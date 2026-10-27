"""Collection paths and immutable qualification configuration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from swarm_mine.models import CollectionConfig


def digest_json(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def project_root(start: Path) -> Path:
    """Find the nearest project marker, otherwise use the invocation directory."""
    start = start.resolve()
    for directory in (start, *start.parents):
        if any(
            (directory / marker).exists() for marker in (".git", "pyproject.toml", "package.json")
        ):
            return directory
    return start


class Workspace:
    """One collection, separate from the installed skill."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.config = CollectionConfig.model_validate_json((self.root / "config.json").read_text())
        self.database = self.root / "registry.sqlite3"
        self.work = self.root / "work"
        self.assets = self.root / "assets"

    @classmethod
    def initialize(cls, config: CollectionConfig, root: Path | None = None) -> Workspace:
        destination = (
            (root or project_root(Path.cwd()) / "swarm-mine" / config.name).expanduser().resolve()
        )
        skill_root = Path(__file__).resolve().parents[2]
        if destination.is_relative_to(skill_root):
            raise ValueError("collection data must live outside the installed skill")
        config_path = destination / "config.json"
        if config_path.exists():
            existing = CollectionConfig.model_validate_json(config_path.read_text())
            if existing != config:
                raise ValueError(
                    "existing collection has different configuration; choose a new path"
                )
        else:
            if destination.exists() and any(destination.iterdir()):
                raise ValueError("destination is not empty and is not a collection")
            destination.mkdir(parents=True, exist_ok=True)
            with config_path.open("x") as handle:
                handle.write(config.model_dump_json(indent=2) + "\n")
        for name in ("assets", "classifier", "seeds", "work/scratch", "work/jobs", "work/probes"):
            (destination / name).mkdir(parents=True, exist_ok=True)
        return cls(destination)

    @property
    def qualification_id(self) -> str:
        """Bind decisions to the target, formats, and classifier configuration."""
        return digest_json(self.config.model_dump(mode="json", exclude={"workers"}))

    def resolve(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        return (candidate if candidate.is_absolute() else self.root / candidate).resolve()

    def classifier_id(self) -> str:
        """Bind the queue to actual classifier and custom processor file bytes."""
        from swarm_mine.hashing import sha256_file

        config = self.config.classifier
        names = list(config.files)
        if config.artifact:
            names.append(config.artifact)
        for fmt in self.config.formats:
            if fmt.processor == "command":
                # Custom preparation scripts must be included in classifier.files.
                if not config.files:
                    raise ValueError("declare custom processor files in classifier.files")
        files = {name: sha256_file(self.resolve(name)) for name in names}
        return digest_json({"configuration": self.qualification_id, "files": files})
