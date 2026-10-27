"""Source and resource command handlers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from swarm_mine.models import ResourceInput
from swarm_mine.store.sqlite import SqliteRegistry


def jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if line.strip():
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("each row must be a JSON object")
                rows.append(row)
            except ValueError as error:
                raise ValueError(f"{path}:{number}: {error}") from error
    return rows


def source_command(args: argparse.Namespace, store: SqliteRegistry) -> Any:
    if args.action == "list":
        return {"sources": store.sources(), **store.stats()}
    if args.action == "show":
        return {
            "sources": store.sources(args.source),
            "observations": store.observations(args.source),
        }
    if args.action == "add":
        store.source_add(
            args.source,
            display_name=args.display_name,
            rights_tier=args.rights_tier,
            access_urls=args.access_url,
            access_notes=args.access_notes,
            status=args.status,
            priority=args.priority,
            min_interval_seconds=args.min_interval,
        )
    elif args.action == "update":
        changes = {
            field: getattr(args, field)
            for field in ("status", "priority", "access_notes")
            if getattr(args, field) is not None
        }
        if args.discovery_state is not None:
            changes["discovery_state"] = json.loads(args.discovery_state)
        if args.min_interval is not None:
            changes["min_interval_seconds"] = args.min_interval
        store.source_update(args.source, **changes)
    elif args.action == "exhaust":
        store.source_update(args.source, status="exhausted", exhaustion_notes=args.reason)
        store.log(args.source, args.agent, args.reason)
    elif args.action == "log":
        store.log(args.source, args.agent, args.note)
    return {"sources": store.sources(args.source)}


def resource_command(args: argparse.Namespace, store: SqliteRegistry) -> Any:
    if args.action == "list":
        return {
            "resources": store.list_resources(
                source=args.source,
                status=args.status,
                url_like=args.url_like,
                notes_like=args.notes_like,
                limit=args.limit,
            )
        }
    if args.action == "release":
        return {"released": store.release(args.agent, args.url)}
    if args.action == "add":
        if bool(args.url) == bool(args.jsonl):
            raise ValueError("provide exactly one of --url and --jsonl")
        raw = (
            jsonl(args.jsonl)
            if args.jsonl
            else [
                {
                    "url": args.url,
                    "score": args.score,
                    "kind": args.kind,
                    "notes": args.notes,
                    "published_at": args.published_at,
                }
            ]
        )
        rows = []
        for number, row in enumerate(raw, 1):
            try:
                rows.append(ResourceInput.model_validate(row))
            except ValueError as error:
                raise ValueError(f"{args.jsonl or 'inline'}:{number}: {error}") from error
        return {"inserted": store.add_resources(args.source, rows)}
    if bool(args.url) == bool(args.jsonl):
        raise ValueError("provide exactly one of --url and --jsonl")
    rows = (
        jsonl(args.jsonl)
        if args.jsonl
        else [
            {
                "url": args.url,
                "resolution": args.resolution,
                "notes": args.notes,
            }
        ]
    )
    # Validate the entire buffer before the first write.
    for row in rows:
        if not isinstance(row.get("url"), str) or row.get("resolution") not in (
            "failed",
            "excluded",
        ):
            raise ValueError("mark rows require url and resolution=failed|excluded")
    return {
        "outcomes": [
            {
                "url": row["url"],
                "updated": store.mark(
                    row["url"],
                    row["resolution"],
                    row.get("notes"),
                ),
            }
            for row in rows
        ]
    }
