#!/usr/bin/env python3
"""Check and update diagram review checkpoints against Git's staging area."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

CONTRACT_DIR = "docs/graphviz-contracts/"
METADATA_DIR = CONTRACT_DIR + "metadata/"
ROUTER_FILE = CONTRACT_DIR + "DIAGRAMS.md"
CHECKPOINT_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
DIAGRAM_NAME_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+\Z")
NUMBER_OR_VERSION_RE = re.compile(r"(?:[0-9]+|v[0-9]+)\Z")


class ContractError(Exception):
    """An invalid contract or Git state prevents a reliable check."""


@dataclass(frozen=True)
class IndexFile:
    mode: str
    oid: str


@dataclass(frozen=True)
class Diagram:
    name: str
    filename: str
    raw: bytes
    data: dict
    paths: tuple[str, ...]


def git(root: Path | None, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if result.returncode:
        raise ContractError(result.stderr.decode("utf-8", "replace").strip() or "Git command failed")
    return result.stdout


def repository_root() -> Path:
    return Path(git(None, "rev-parse", "--show-toplevel").decode("utf-8", "surrogateescape").rstrip("\n"))


def read_index(root: Path) -> dict[str, IndexFile]:
    files = {}
    for record in git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if not record:
            continue
        header, path = record.split(b"\t", 1)
        mode, oid, stage = header.decode("ascii").split()
        if stage != "0":
            raise ContractError("Resolve unmerged files before checking diagram checkpoints.")
        files[path.decode("utf-8", "surrogateescape")] = IndexFile(mode, oid)
    return files


def blob(root: Path, entry: IndexFile) -> bytes:
    if entry.mode not in {"100644", "100755", "120000"}:
        raise ContractError(f"Unsupported Git file mode {entry.mode}; submodules cannot be covered.")
    return git(root, "cat-file", "blob", entry.oid)


def valid_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        return False
    parts = value.removesuffix("/").split("/")
    return all(part not in {"", ".", ".."} for part in parts) and not PurePosixPath(value).is_absolute()


def read_diagrams(root: Path, files: dict[str, IndexFile], *, allow_empty: bool = False) -> list[Diagram]:
    diagrams = []
    for filename, entry in sorted(files.items()):
        if not filename.startswith(METADATA_DIR):
            continue
        relative = filename[len(METADATA_DIR):]
        if "/" in relative or not relative.endswith(".json"):
            continue
        if entry.mode not in {"100644", "100755"}:
            raise ContractError(f"{filename}: metadata must be a regular file.")
        raw = blob(root, entry)
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ContractError(f"{filename}: invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ContractError(f"{filename}: expected a JSON object.")
        paths = data.get("paths")
        if not isinstance(paths, list) or not paths or not all(valid_path(path) for path in paths):
            raise ContractError(f"{filename}: paths must be a nonempty list of repository-relative file or directory paths.")
        if len(set(paths)) != len(paths):
            raise ContractError(f"{filename}: paths must not contain duplicates.")
        if any(path.startswith(METADATA_DIR) or (path.endswith("/") and METADATA_DIR.startswith(path)) for path in paths):
            raise ContractError(f"{filename}: paths cannot cover diagram metadata itself.")
        diagrams.append(Diagram(relative[:-5], filename, raw, data, tuple(paths)))
    if not diagrams and not allow_empty:
        raise ContractError(f"No staged diagram metadata found in {METADATA_DIR}.")
    return diagrams


def covers(pattern: str, path: str) -> bool:
    return path.startswith(pattern) if pattern.endswith("/") else path == pattern


def checkpoint(root: Path, files: dict[str, IndexFile], diagram: Diagram) -> str:
    digest = hashlib.sha256()

    def add(value: bytes) -> None:
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)

    add(b"graphviz-contract-v1")
    for path in sorted(diagram.paths):
        add(path.encode("utf-8"))
    add(b"files")
    for path, entry in sorted(files.items()):
        if any(covers(pattern, path) for pattern in diagram.paths):
            add(path.encode("utf-8", "surrogateescape"))
            add(entry.mode.encode("ascii"))
            add(blob(root, entry))
    return "sha256:" + digest.hexdigest()


def valid_diagram_name(name: str) -> bool:
    """Check scope-subject syntax and reject numeric date/order and vN version tokens."""
    return bool(DIAGRAM_NAME_RE.fullmatch(name)) and not any(
        NUMBER_OR_VERSION_RE.fullmatch(token) for token in name.split("-")
    )


def check_router_names(root: Path, files: dict[str, IndexFile], names: set[str]) -> list[str]:
    """Match names in the staged router table to the diagram basenames."""
    entry = files.get(ROUTER_FILE)
    if entry is None:
        return [f"{ROUTER_FILE}: missing router; stage a Name/Description table"]
    if entry.mode not in {"100644", "100755"}:
        return [f"{ROUTER_FILE}: router must be a regular file"]
    try:
        lines = [line.strip() for line in blob(root, entry).decode("utf-8").splitlines() if line.strip()]
    except UnicodeDecodeError:
        return [f"{ROUTER_FILE}: router must be UTF-8 text"]
    rows = [line.strip("|").split("|", 1) for line in lines]
    if (len(rows) < 2 or [cell.strip() for cell in rows[0]] != ["Name", "Description"]
            or len(rows[1]) != 2
            or not all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in rows[1])):
        return [f"{ROUTER_FILE}: expected a Name/Description table"]
    failures: list[str] = []
    router_names: list[str] = []
    for row in rows[2:]:
        if len(row) != 2 or not row[0].strip():
            failures.append(f"{ROUTER_FILE}: expected a named table row")
            continue
        name = row[0].strip()
        if name.startswith("`") and name.endswith("`"):
            name = name[1:-1]
        router_names.append(name)
    for name, count in sorted(Counter(router_names).items()):
        if count > 1:
            failures.append(f"{name}: duplicate router entry")
        if name not in names:
            failures.append(f"{name}: router entry has no diagram with that basename")
    for name in sorted(names - set(router_names)):
        failures.append(f"{name}: missing router entry")
    return failures


def check(root: Path, files: dict[str, IndexFile], diagrams: list[Diagram]) -> int:
    failures: list[str] = []
    kinds = {"DOT source": ("dot/", ".dot"), "PNG render": ("png/", ".png"),
             "metadata": ("metadata/", ".json")}
    names_by_kind: dict[str, set[str]] = {}
    for kind, (directory, extension) in kinds.items():
        prefix = CONTRACT_DIR + directory
        names_by_kind[kind] = set()
        for filename in files:
            if filename.startswith(prefix) and filename.lower().endswith(extension):
                names_by_kind[kind].add(filename[len(prefix):-len(extension)])
                if not filename.endswith(extension):
                    failures.append(f"{filename}: use lowercase {extension} extension")
    names = set().union(*names_by_kind.values())
    if not names:
        failures.append(f"No staged diagram files found in {CONTRACT_DIR}.")
    for name in sorted(names):
        if not valid_diagram_name(name):
            failures.append(
                f"{name}: invalid diagram name; use lowercase scope-subject words separated by "
                "single hyphens, without numeric date/order tokens or vN versions"
            )
        for kind, (directory, extension) in kinds.items():
            if name not in names_by_kind[kind]:
                failures.append(f"{name}: missing {kind} ({CONTRACT_DIR}{directory}{name}{extension})")
    failures.extend(check_router_names(root, files, names))
    for diagram in diagrams:
        for path in diagram.paths:
            if not any(covers(path, filename) for filename in files):
                failures.append(f"{diagram.name}: coverage path matches no staged files: {path}")
        saved = diagram.data.get("checkpoint")
        if not isinstance(saved, str) or not CHECKPOINT_RE.fullmatch(saved):
            failures.append(f"{diagram.name}: missing or invalid checkpoint")
        elif saved != checkpoint(root, files, diagram):
            failures.append(f"{diagram.name}: covered staged files changed")
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        print("Fix the reported diagram issues and stage the relevant files.", file=sys.stderr)
        return 1
    print(f"Diagram health checks passed ({len(diagrams)} checked).")
    return 0


def update(root: Path, files: dict[str, IndexFile], diagrams: list[Diagram], names: list[str]) -> int:
    by_name = {diagram.name: diagram for diagram in diagrams}
    missing = sorted(set(names) - by_name.keys())
    if missing:
        raise ContractError("Unknown diagrams: " + ", ".join(missing))
    updates = []
    for name in dict.fromkeys(names):
        diagram = by_name[name]
        path = root / diagram.filename
        try:
            current = path.read_bytes()
        except OSError as exc:
            raise ContractError(f"{diagram.filename}: cannot read working file: {exc}") from exc
        if path.is_symlink() or current != diagram.raw:
            raise ContractError(f"{diagram.filename}: stage its working changes before updating the checkpoint.")
        data = dict(diagram.data)
        data["checkpoint"] = checkpoint(root, files, diagram)
        updates.append((path, (json.dumps(data, indent=2, ensure_ascii=True) + "\n").encode()))
    for path, content in updates:
        path.write_bytes(content)
        print(f"Updated {path.relative_to(root)}; stage this file to include the checkpoint.")
    return 0


def find(root: Path, diagrams: list[Diagram], paths: list[str], staged: bool) -> int:
    if staged:
        paths = [p.decode("utf-8", "surrogateescape") for p in git(
            root, "diff", "--cached", "--name-only", "--no-renames", "-z", "--"
        ).split(b"\0") if p]
    elif not paths:
        raise ContractError("Provide repository-relative paths or use --staged.")
    if any(not valid_path(path) or path.endswith("/") for path in paths):
        raise ContractError("Changed paths must be repository-relative file paths.")
    matches = {
        diagram.name: sorted(path for path in set(paths) if any(covers(p, path) for p in diagram.paths))
        for diagram in diagrams
    }
    print(json.dumps({name: paths for name, paths in matches.items() if paths}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="check staged diagram names, router, files, coverage paths, and checkpoints")
    refresh = commands.add_parser("checkpoint", help="update checkpoints after reviewing diagrams")
    refresh.add_argument("diagrams", nargs="+", help="metadata filenames without .json")
    search = commands.add_parser("find", help="find diagrams covering changed paths")
    search.add_argument("--staged", action="store_true", help="use staged changes, including both sides of renames")
    search.add_argument("paths", nargs="*", help="changed repository-relative file paths")
    args = parser.parse_args()
    try:
        if args.command == "find" and args.staged and args.paths:
            raise ContractError("Use either --staged or explicit paths, not both.")
        root = repository_root()
        files = read_index(root)
        diagrams = read_diagrams(root, files, allow_empty=args.command == "check")
        if args.command == "check":
            return check(root, files, diagrams)
        if args.command == "checkpoint":
            return update(root, files, diagrams, args.diagrams)
        return find(root, diagrams, args.paths, args.staged)
    except (ContractError, OSError) as exc:
        print(f"graphviz-contract: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
