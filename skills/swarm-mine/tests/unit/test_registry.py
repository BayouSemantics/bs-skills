from __future__ import annotations

import time

import pytest
from swarm_mine.models import ResourceInput
from swarm_mine.store.sqlite import SqliteRegistry
from swarm_mine.workspace import Workspace


def test_registration_is_idempotent_and_host_scoped(store: SqliteRegistry) -> None:
    item = ResourceInput(url="https://example.org/a.txt", score=90)
    assert store.add_resources("example.org", [item]) == 1
    assert store.add_resources("example.org", [item.model_copy(update={"score": 1})]) == 0
    assert store.resource(item.url)["score"] == 90
    with pytest.raises(ValueError, match="host differs"):
        store.add_resources("example.org", [ResourceInput(url="https://elsewhere.org/a")])
    with pytest.raises(ValueError, match="source exists"):
        store.source_add(
            "example.org",
            display_name="x",
            rights_tier="public",
            access_urls=["https://example.org"],
        )


def test_claim_orders_score_recency_and_prevents_duplicates(store: SqliteRegistry) -> None:
    rows = [
        ResourceInput(url=f"https://example.org/{n}", score=score, published_at=date)
        for n, score, date in [
            (1, 90, "2020-01-01T00:00:00Z"),
            (2, 90, "2024-01-01T00:00:00Z"),
            (3, 10, None),
        ]
    ]
    store.add_resources("example.org", rows)
    first = store.claim("agent-a", min_score=50)
    second = store.claim("agent-b", min_score=50)
    assert first["original_url"] == rows[1].url
    assert second["original_url"] == rows[0].url
    assert store.claim("agent-c", min_score=50) is None
    assert store.release("agent-a") == 1
    assert store.claim("agent-c", min_score=50)["original_url"] == rows[1].url


def test_expired_claim_is_reclaimed_and_old_owner_cannot_complete(
    store: SqliteRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store.add_resources("example.org", [ResourceInput(url="https://example.org/a")])
    first = store.claim("a", ttl_seconds=1)
    future = time.time() + 2
    monkeypatch.setattr("swarm_mine.store.sqlite.time.time", lambda: future)
    second = store.claim("b")
    assert first["claim_token"] != second["claim_token"]
    with pytest.raises(ValueError, match="lease lost"):
        store.complete(first, [], "a" * 64)
    assert store.resource(first["original_url"])["claimed_by"] == "b"


def test_completion_is_atomic_and_preserves_covered_rows(store: SqliteRegistry) -> None:
    url = "https://example.org/a"
    store.add_resources("example.org", [ResourceInput(url=url)])
    claim = store.claim("a")
    file = {
        "content_sha256": "a" * 64,
        "byte_size": 10,
        "eligible": True,
        "accepted_units": 2,
        "classifier_id": "v1",
    }
    store.complete(claim, [file], file["content_sha256"])
    assert store.resource(url)["status"] == "covered"
    assert store.resource(url)["claimed_by"] is None
    assert not store.mark(url, "failed")
    assert store.claim("b") is None
    assert store.stats()["coverage"][0]["accepted_units"] == 2


def test_host_lock_is_shared_and_enforces_finish_spacing(
    workspace: Workspace,
    store: SqliteRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = SqliteRegistry(workspace.database)
    assert store.acquire_host("example.org", "one", interval=1) == 0
    assert other.acquire_host("example.org", "two", interval=1) > 0
    store.release_host("example.org", "wrong", interval=1)
    assert other.acquire_host("example.org", "two", interval=1) > 0
    store.release_host("example.org", "one", interval=1)
    assert other.acquire_host("example.org", "two", interval=1) > 0
    future = time.time() + 2
    monkeypatch.setattr("swarm_mine.store.sqlite.time.time", lambda: future)
    assert other.acquire_host("example.org", "two", interval=1) == 0


def test_filters_treat_wildcards_literally(store: SqliteRegistry) -> None:
    store.add_resources(
        "example.org",
        [
            ResourceInput(url="https://example.org/a", notes="20% yield"),
            ResourceInput(url="https://example.org/b", notes="other"),
        ],
    )
    assert len(store.list_resources(notes_like="%")) == 1


def test_configuration_cannot_reuse_previous_decisions(store: SqliteRegistry) -> None:
    with pytest.raises(ValueError, match="qualification_id changed"):
        store.bind("qualification_id", "different target")


def test_sources_can_enforce_stricter_request_spacing(store: SqliteRegistry) -> None:
    store.source_update("example.org", min_interval_seconds=10)
    assert store.host_interval("example.org", 1) == 10
    assert store.host_interval("unregistered.org", 2) == 2
