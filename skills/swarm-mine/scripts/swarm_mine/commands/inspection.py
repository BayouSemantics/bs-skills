"""Read-only coverage inspection and conservative temporary-file cleanup."""

from __future__ import annotations

import json
import shutil
import uuid
from typing import Any

from swarm_mine.fetch import Fetcher
from swarm_mine.hashing import sha256_file
from swarm_mine.processing.assets import AssetPreparer, UnsupportedFormat, identify
from swarm_mine.store.sqlite import SqliteRegistry
from swarm_mine.workspace import Workspace


def probe(
    workspace: Workspace,
    fetcher: Fetcher,
    url: str,
    *,
    terms: list[str],
    discard: bool,
) -> dict[str, Any]:
    directory = workspace.work / "probes" / uuid.uuid4().hex
    directory.mkdir(parents=True)
    path = directory / "download"
    result = fetcher.download(url, path, max_bytes=workspace.config.max_download_bytes)
    report: dict[str, Any] = result.model_dump()
    try:
        if result.ok:
            report["content_sha256"] = sha256_file(path)
            report["path"] = str(path)
            try:
                fmt = identify(
                    path, result.final_url, result.content_type, workspace.config.formats
                )
                report["format"] = fmt.name
                if fmt.processor == "zip":
                    import zipfile

                    with zipfile.ZipFile(path) as archive:
                        report["members"] = archive.namelist()[
                            : workspace.config.max_archive_members
                        ]
                elif fmt.processor == "pdf":
                    from swarm_mine.processing.document import page_count
                    from swarm_mine.processing.text import extract_page_text

                    report["page_count"] = page_count(path)
                    texts = [
                        extract_page_text(path, n)
                        for n in range(
                            1,
                            min(report["page_count"], 20) + 1,
                        )
                    ]
                    report.update(_text_report(texts, terms))
                else:
                    units = AssetPreparer(workspace).prepare(path, fmt, directory / "units")
                    report.update(_text_report([u.text for u in units], terms))
            except UnsupportedFormat as error:
                report["format_error"] = str(error)
        return report
    finally:
        if discard:
            shutil.rmtree(directory)
            report.pop("path", None)


def _text_report(texts: list[str], terms: list[str]) -> dict[str, Any]:
    return {
        "text_sample": " ".join(texts)[:1200],
        "units_sampled": len(texts),
        "term_hits": {
            term: [n for n, text in enumerate(texts, 1) if term.casefold() in text.casefold()]
            for term in terms
        },
    }


def reconcile(workspace: Workspace, store: SqliteRegistry, *, sweep: bool) -> dict[str, Any]:
    """Remove only temporary jobs proven inactive; retained assets are reported."""
    inactive = []
    swept = []
    active = store.active_claim_tokens()
    for directory in (workspace.work / "jobs").glob("*/*"):
        if directory.name not in active and directory.is_dir():
            inactive.append(str(directory))
            if sweep:
                shutil.rmtree(directory)
                swept.append(str(directory))
    unknown = []
    missing = []
    hashes = store.retained_hashes()
    for path in workspace.assets.iterdir():
        if path.is_dir() and path.name not in hashes:
            unknown.append(str(path))
    for digest in hashes:
        metadata = workspace.assets / digest / "metadata.json"
        if not metadata.is_file():
            missing.append(digest)
        else:
            value = json.loads(metadata.read_text())
            if not (metadata.parent / value["source_file"]).is_file():
                missing.append(digest)
    return {
        "inactive_jobs": inactive,
        "swept": swept,
        "unrecorded_assets": unknown,
        "missing_assets": missing,
    }
