"""JSON command interface for collection setup, mining, and registry curation."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from swarm_mine.classification import check_classifier
from swarm_mine.commands.inspection import probe, reconcile
from swarm_mine.commands.registry import resource_command, source_command
from swarm_mine.driver import EventLog, MiningDriver
from swarm_mine.fetch import PoliteFetcher
from swarm_mine.identity import mint_agent_identity
from swarm_mine.models import CollectionConfig
from swarm_mine.store.sqlite import SqliteRegistry
from swarm_mine.workspace import Workspace, project_root


def _positive(value: str) -> int:
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="swarm-mine")
    parser.add_argument("--workspace", type=Path, help="absolute collection directory")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("config-schema", help="emit the collection configuration JSON schema")
    commands.add_parser("classifier-contract", help="emit classifier and processor JSON contracts")
    commands.add_parser("new-identity", help="mint one identity for the whole shift")
    init = commands.add_parser("init", help="initialize or resume an identical collection")
    init.add_argument("--config", type=Path, required=True)
    init.add_argument("--project-root", type=Path)
    commands.add_parser("check", help="check classifier files and held-out evaluation")
    train = commands.add_parser(
        "train-text",
        description=(
            'Train a small TF-IDF classifier. JSONL rows: {"text":"...", "label":"accept|reject", '
            '"split":"train|validation", "group":"original-document-id"}. '
            "Hold original documents/groups out together. Requires the text-classifier extra."
        ),
    )
    train.add_argument("--examples", type=Path, required=True)
    for command in ("run-pool", "run-source", "run-url"):
        run = commands.add_parser(command)
        run.add_argument("--agent", required=True)
        run.add_argument("--transport", choices=("auto", "httpx", "curl-http1"), default="auto")
        run.add_argument("--events-out", type=Path)
        if command != "run-url":
            run.add_argument("--limit", type=_positive)
            run.add_argument("--min-score", type=float)
            run.add_argument("--deadline", type=_positive, help="seconds, checked between URLs")
        if command != "run-pool":
            run.add_argument("--source", required=True)
        if command == "run-url":
            run.add_argument("--url", required=True)
    triage = commands.add_parser("probe", help="inspect a URL without registering coverage")
    triage.add_argument("--url", required=True)
    triage.add_argument("--term", action="append", default=[])
    triage.add_argument("--discard", action="store_true")
    triage.add_argument("--transport", choices=("auto", "httpx", "curl-http1"), default="auto")
    stats = commands.add_parser("stats")
    stats.add_argument("--since", help="elapsed window, e.g. 3.5h, 30m, 2d")
    cleanup = commands.add_parser("reconcile")
    cleanup.add_argument("--sweep", action="store_true", help="delete inactive temporary jobs")
    source = commands.add_parser("source").add_subparsers(dest="action", required=True)
    for action in ("list", "show", "add", "update", "log", "exhaust"):
        sub = source.add_parser(action)
        if action != "list":
            sub.add_argument("--source", required=True)
        if action in ("add", "update"):
            sub.add_argument("--min-interval", type=float, default=1 if action == "add" else None)
            sub.add_argument(
                "--status",
                choices=("active", "exploratory", "exhausted", "blocked"),
                default="exploratory" if action == "add" else None,
            )
            sub.add_argument("--priority", type=int, default=100 if action == "add" else None)
            sub.add_argument("--access-notes", default="" if action == "add" else None)
        if action == "add":
            sub.add_argument("--display-name", required=True)
            sub.add_argument("--rights-tier", required=True)
            sub.add_argument("--access-url", action="append", required=True)
        if action == "update":
            sub.add_argument("--discovery-state")
        if action in ("log", "exhaust"):
            sub.add_argument("--agent", required=True)
            sub.add_argument("--note" if action == "log" else "--reason", required=True)
    resource = commands.add_parser("resource").add_subparsers(dest="action", required=True)
    for action in ("add", "list", "release", "mark"):
        sub = resource.add_parser(action)
        if action in ("add", "list"):
            sub.add_argument("--source", required=action == "add")
        if action != "list":
            sub.add_argument("--url")
        if action in ("add", "mark"):
            sub.add_argument("--jsonl", type=Path)
            sub.add_argument("--notes")
        if action == "add":
            sub.add_argument("--score", type=float)
            sub.add_argument("--kind", choices=("candidate", "retry"), default="candidate")
            sub.add_argument("--published-at")
        if action == "mark":
            sub.add_argument("--resolution", choices=("failed", "excluded"))
        if action == "release":
            sub.add_argument("--agent", required=True)
        if action == "list":
            sub.add_argument("--status", choices=("unmined", "covered", "failed", "excluded"))
            sub.add_argument("--url-like")
            sub.add_argument("--notes-like")
            sub.add_argument("--limit", type=_positive, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = dispatch(args)
        print(json.dumps(result, default=str))
        return 0
    except Exception as error:
        print(json.dumps({"error": str(error), "type": type(error).__name__}))
        return 1


def dispatch(args: argparse.Namespace) -> dict:
    if args.command == "new-identity":
        return {"agent": mint_agent_identity()}
    if args.command == "config-schema":
        return CollectionConfig.model_json_schema()
    if args.command == "classifier-contract":
        return {
            "execution": "local argv command, no shell; cwd is workspace; JSON stdin/stdout",
            "classifier_input": {
                "target": "description",
                "units": [
                    {
                        "id": "asset",
                        "path": "/absolute/file",
                        "text": "extracted text",
                        "media_type": "text/plain",
                        "page_number": None,
                    }
                ],
            },
            "classifier_output": {
                "decisions": [
                    {"unit_id": "asset", "decision": "accept", "score": 0.9, "reason": "matches"}
                ]
            },
            "classifier_rules": "exactly one accept/reject decision per unit; score is 0..1",
            "processor_input": {
                "asset": "/absolute/file",
                "format": "configured format name",
                "output_dir": "/absolute/work/path",
                "target": "description",
            },
            "processor_output": {
                "units": [
                    {
                        "id": "asset",
                        "path": "/absolute/work/path/unit",
                        "media_type": "text/plain",
                        "text": "extracted text",
                    }
                ]
            },
            "processor_rules": "unique unit ids; existing absolute files inside output_dir",
        }
    if args.command == "init":
        config = CollectionConfig.model_validate_json(args.config.read_text())
        root = (
            args.workspace
            or (args.project_root or project_root(Path.cwd())) / "swarm-mine" / config.name
        )
        workspace = Workspace.initialize(config, root)
        SqliteRegistry(workspace.database).initialize(workspace.qualification_id)
        return {
            "workspace": str(workspace.root),
            "database": str(workspace.database),
            "workers": [w.model_dump() for w in config.workers],
        }
    if args.workspace is None:
        raise ValueError("--workspace is required; pass the absolute collection path")
    workspace = Workspace(args.workspace)
    store = SqliteRegistry(workspace.database)
    if not workspace.database.is_file():
        raise ValueError("collection is not initialized; run init")
    store.bind("qualification_id", workspace.qualification_id)
    if args.command == "check":
        return check_classifier(workspace)
    if args.command == "train-text":
        from swarm_mine.training import train_text

        return train_text(workspace, workspace.resolve(args.examples))
    if args.command == "source":
        return source_command(args, store)
    if args.command == "resource":
        if getattr(args, "jsonl", None):
            args.jsonl = workspace.resolve(args.jsonl)
        return resource_command(args, store)
    if args.command == "stats":
        since = 0.0
        if args.since:
            match = re.fullmatch(r"(\d+(?:\.\d+)?)([smhd])", args.since)
            if not match:
                raise ValueError("since must look like 30m, 3.5h, or 2d")
            since = (
                time.time() - float(match[1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[match[2]]
            )
        return store.stats(since)
    if args.command == "reconcile":
        return reconcile(workspace, store, sweep=args.sweep)
    fetcher = PoliteFetcher(
        store, interval=workspace.config.min_interval_seconds, transport=args.transport
    )
    try:
        if args.command == "probe":
            return probe(workspace, fetcher, args.url, terms=args.term, discard=args.discard)
        events_path = workspace.resolve(args.events_out) if args.events_out else None
        if events_path and not events_path.is_relative_to(workspace.work / "scratch"):
            raise ValueError("event traces belong in work/scratch inside the collection")
        driver = MiningDriver(workspace, store, fetcher=fetcher, events=EventLog(events_path))
        if args.command == "run-url":
            return driver.run_url(args.url, source=args.source, agent=args.agent)
        return driver.run_pool(
            agent=args.agent,
            source=getattr(args, "source", None),
            limit=args.limit,
            min_score=args.min_score,
            deadline=args.deadline,
        )
    finally:
        fetcher.close()


if __name__ == "__main__":
    sys.exit(main())
