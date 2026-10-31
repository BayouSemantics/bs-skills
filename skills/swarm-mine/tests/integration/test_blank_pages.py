from __future__ import annotations

import pymupdf
import pytest
from swarm_mine.driver import MiningDriver
from swarm_mine.models import ResourceInput
from swarm_mine.store.sqlite import SqliteRegistry
from swarm_mine.training import train_text
from swarm_mine.workspace import Workspace
from test_driver import MemoryFetcher
from test_training import examples, text_workspace  # noqa: F401

URL = "https://example.org/a.pdf"


def pdf(*pages: str) -> bytes:
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_text((50, 50), text)
    body = document.tobytes()
    document.close()
    return body


@pytest.mark.parametrize(
    ("pages", "outcome", "accepted"),
    [
        (("target invoice payment amount total", ""), "retained", 1),
        (("", ""), "recorded_ineligible", 0),
    ],
)
def test_text_classifier_rejects_pages_without_text(
    text_workspace: Workspace,  # noqa: F811
    pages: tuple[str, ...],
    outcome: str,
    accepted: int,
) -> None:
    path, _ = examples(text_workspace)
    assert train_text(text_workspace, path)["passed"]
    store = SqliteRegistry(text_workspace.database)
    store.initialize(text_workspace.qualification_id)
    store.source_add(
        "example.org",
        display_name="Example",
        rights_tier="public_record",
        access_urls=["https://example.org/"],
    )
    store.add_resources("example.org", [ResourceInput(url=URL)])
    fetcher = MemoryFetcher(pdf(*pages), "application/pdf")
    driver = MiningDriver(text_workspace, store, fetcher=fetcher)
    result = driver.run_pool(agent="a", limit=5)
    assert result["outcomes"] == {outcome: 1}, result
    assert fetcher.calls == 1
    assert store.resource(URL)["status"] == "covered"
