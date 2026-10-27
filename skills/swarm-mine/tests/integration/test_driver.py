from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import fitz
import pytest
from swarm_mine.driver import MiningDriver
from swarm_mine.fetch import FetchOutcome
from swarm_mine.models import CollectionConfig, Format
from swarm_mine.store.sqlite import SqliteRegistry
from swarm_mine.workspace import Workspace


class MemoryFetcher:
    def __init__(self, body: bytes, content_type: str = "text/plain", status: int = 200) -> None:
        self.body, self.content_type, self.status = body, content_type, status
        self.calls = 0

    def download(self, url: str, destination: Path, *, max_bytes: int) -> FetchOutcome:
        self.calls += 1
        if self.status != 200:
            return FetchOutcome(ok=False, http_status=self.status, final_url=url, error="fixture")
        destination.write_bytes(self.body)
        return FetchOutcome(
            ok=True, final_url=url, byte_size=len(self.body), content_type=self.content_type
        )

    def close(self) -> None:
        pass


def test_retains_local_assets_and_deduplicates_urls_and_bytes(
    workspace: Workspace,
    store: SqliteRegistry,
) -> None:
    fetcher = MemoryFetcher(b"target invoice")
    driver = MiningDriver(workspace, store, fetcher=fetcher)
    result = driver.run_url("https://example.org/a.txt", source="example.org", agent="a")
    assert result["outcome"] == "retained"
    directory = workspace.assets / result["content_sha256"]
    assert (directory / "source.txt").read_bytes() == b"target invoice"
    assert (
        driver.run_url("https://example.org/a.txt", source="example.org", agent="a")["reason"]
        == "covered"
    )
    assert fetcher.calls == 1
    assert (
        driver.run_url("https://example.org/b.txt", source="example.org", agent="a")["outcome"]
        == "recorded_duplicate"
    )
    assert len(list(workspace.assets.iterdir())) == 1
    assert not list((workspace.work / "jobs").glob("*/*"))


def test_pdf_keeps_original_and_only_accepted_pages(
    workspace: Workspace, store: SqliteRegistry
) -> None:
    document = fitz.open()
    for text in ("target page", "irrelevant page"):
        document.new_page().insert_text((50, 50), text)
    body = document.tobytes()
    document.close()
    driver = MiningDriver(workspace, store, fetcher=MemoryFetcher(body, "application/pdf"))
    result = driver.run_url("https://example.org/a.pdf", source="example.org", agent="a")
    assert result["accepted_units"] == 1
    directory = workspace.assets / result["content_sha256"]
    metadata = json.loads((directory / "metadata.json").read_text())
    assert metadata["units"][0]["page_number"] == 1
    assert len(list(directory.glob("*.png"))) == 1
    assert (directory / "source.pdf").read_bytes() == body


def test_archive_records_container_url_and_retains_matching_members(
    workspace: Workspace,
    store: SqliteRegistry,
) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("folder/yes.txt", "target member")
        archive.writestr("no.txt", "irrelevant")
    driver = MiningDriver(
        workspace, store, fetcher=MemoryFetcher(buffer.getvalue(), "application/zip")
    )
    result = driver.run_url("https://example.org/a.zip", source="example.org", agent="a")
    assert result["accepted_units"] == 1
    assert len(store.list_resources()) == 1
    assert len(list(workspace.assets.iterdir())) == 2
    metadata = json.loads(
        (workspace.assets / result["content_sha256"] / "metadata.json").read_text()
    )
    assert len(metadata["members"]) == 1


def test_publication_failure_leaves_url_retryable(
    workspace: Workspace,
    store: SqliteRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = MiningDriver(workspace, store, fetcher=MemoryFetcher(b"target"))

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(driver.publisher, "publish", fail)
    with pytest.raises(OSError, match="disk full"):
        driver.run_url("https://example.org/a.txt", source="example.org", agent="a")
    row = store.resource("https://example.org/a.txt")
    assert row["status"] == "unmined"
    assert row["claimed_by"] is None
    assert row["content_sha256"] is None


def test_invalid_classifier_result_is_not_coverage(
    workspace: Workspace, store: SqliteRegistry
) -> None:
    (workspace.root / "classifier/predict.py").write_text("print('{\"decisions\": []}')")
    driver = MiningDriver(workspace, store, fetcher=MemoryFetcher(b"target"))
    with pytest.raises(ValueError, match="exactly one"):
        driver.run_url("https://example.org/a.txt", source="example.org", agent="a")
    assert store.resource("https://example.org/a.txt")["status"] == "unmined"
    assert list(workspace.assets.iterdir()) == []


@pytest.mark.parametrize("status,expected", [(403, "unmined"), (404, "failed"), (410, "failed")])
def test_fetch_failure_semantics(
    workspace: Workspace,
    store: SqliteRegistry,
    status: int,
    expected: str,
) -> None:
    driver = MiningDriver(workspace, store, fetcher=MemoryFetcher(b"", status=status))
    driver.run_url("https://example.org/a.txt", source="example.org", agent="a")
    assert store.resource("https://example.org/a.txt")["status"] == expected


def test_changed_classifier_cannot_reuse_the_collection(
    workspace: Workspace, store: SqliteRegistry
) -> None:
    driver = MiningDriver(workspace, store, fetcher=MemoryFetcher(b"unrelated"))
    driver.run_url("https://example.org/a.txt", source="example.org", agent="a")
    with (workspace.root / "classifier/predict.py").open("a") as handle:
        handle.write("\n# new implementation\n")
    with pytest.raises(ValueError, match="classifier_id changed"):
        MiningDriver(workspace, store, fetcher=MemoryFetcher(b"target"))


def test_custom_processor_supports_user_defined_asset_formats(
    tmp_path: Path,
    config: CollectionConfig,
) -> None:
    classifier = config.classifier.model_copy(
        update={
            "files": (*config.classifier.files, "classifier/prepare.py"),
        }
    )
    custom = Format(
        name="custom",
        extensions=(".custom",),
        media_types=("application/x-custom",),
        processor="command",
        command=(config.classifier.command[0], "classifier/prepare.py"),
    )
    updated = config.model_copy(update={"formats": (custom,), "classifier": classifier})
    workspace = Workspace.initialize(updated, tmp_path / "custom")
    (workspace.root / "classifier/predict.py").write_text("""import json,sys
request=json.load(sys.stdin)
print(json.dumps({"decisions":[{"unit_id":u["id"],"decision":"accept", "score":0.9,
"reason":"matches target"} for u in request["units"]]}))
""")
    (workspace.root / "classifier/prepare.py").write_text("""import json,sys
from pathlib import Path
request=json.load(sys.stdin)
path=Path(request["output_dir"])/"prepared.txt"
path.write_text("target extracted from custom bytes")
print(json.dumps({"units":[{"id":"custom-unit","path":str(path),"media_type":"text/plain",
"text":path.read_text()}]}))
""")
    store = SqliteRegistry(workspace.database)
    store.initialize(workspace.qualification_id)
    store.source_add(
        "example.org",
        display_name="Example",
        rights_tier="public_record",
        access_urls=["https://example.org"],
    )
    driver = MiningDriver(
        workspace, store, fetcher=MemoryFetcher(b"custom binary", "application/x-custom")
    )
    result = driver.run_url("https://example.org/a.custom", source="example.org", agent="a")
    assert result["outcome"] == "retained"
    original = workspace.assets / result["content_sha256"] / "source.custom"
    assert original.read_bytes() == b"custom binary"
