"""Content-addressed local publication."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

from swarm_mine.hashing import sha256_file
from swarm_mine.models import Decision, Unit


class AssetPublisher:
    """Publish originals, accepted units, and provenance before recording coverage."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def publish(
        self,
        original: Path,
        *,
        digest: str,
        suffix: str,
        url: str,
        classifier_id: str,
        units: list[Unit],
        decisions: list[Decision],
        member_name: str | None = None,
        members: list[str] | None = None,
    ) -> Path:
        if sha256_file(original) != digest:
            raise ValueError("source file changed before publication")
        destination = self.root / digest
        if destination.exists():
            self._verify(destination, digest, classifier_id)
            return destination
        staging = self.root / f".publish-{uuid.uuid4().hex}"
        staging.mkdir(parents=True)
        try:
            source_name = f"source{suffix or '.bin'}"
            shutil.copyfile(original, staging / source_name)
            by_id = {u.id: u for u in units}
            kept = []
            for decision in decisions:
                if decision.decision != "accept":
                    continue
                unit = by_id[decision.unit_id]
                unit_hash = sha256_file(unit.path)
                name = source_name if unit.path == original else f"{unit_hash}{unit.path.suffix}"
                if name != source_name:
                    shutil.copyfile(unit.path, staging / name)
                kept.append(
                    {
                        **unit.model_dump(mode="json"),
                        "path": name,
                        "sha256": unit_hash,
                        **decision.model_dump(),
                    }
                )
            metadata = {
                "content_sha256": digest,
                "source_file": source_name,
                "source_url": url,
                "archive_member": member_name,
                "members": members or [],
                "classifier_id": classifier_id,
                "units": kept,
            }
            (staging / "metadata.json").write_text(json.dumps(metadata, indent=2))
            for path in staging.iterdir():
                with path.open("rb") as handle:
                    os.fsync(handle.fileno())
            try:
                staging.rename(destination)
            except OSError:
                if not destination.exists():
                    raise
                self._verify(destination, digest, classifier_id)
            descriptor = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return destination
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    @staticmethod
    def _verify(directory: Path, digest: str, classifier_id: str) -> None:
        metadata = json.loads((directory / "metadata.json").read_text())
        if metadata["classifier_id"] != classifier_id:
            raise ValueError("existing asset belongs to another classifier")
        if sha256_file(directory / metadata["source_file"]) != digest:
            raise ValueError("existing retained asset is damaged")
        for unit in metadata["units"]:
            if sha256_file(directory / unit["path"]) != unit["sha256"]:
                raise ValueError("existing retained unit is damaged")
