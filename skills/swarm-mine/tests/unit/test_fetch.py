from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from swarm_mine.fetch import PoliteFetcher
from swarm_mine.store.sqlite import SqliteRegistry


def test_redirects_lease_each_destination_host(store: SqliteRegistry, tmp_path: Path) -> None:
    def serve(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.org":
            return httpx.Response(302, headers={"Location": "https://files.example.net/data"})
        return httpx.Response(200, content=b"target")

    fetcher = PoliteFetcher(store, client=httpx.Client(transport=httpx.MockTransport(serve)))
    try:
        result = fetcher.download("https://example.org/data", tmp_path / "out", max_bytes=100)
        assert result.ok
        assert result.final_url == "https://files.example.net/data"
        with store.connection() as conn:
            assert {r["host"] for r in conn.execute("SELECT * FROM hosts")} == {
                "example.org",
                "files.example.net",
            }
    finally:
        fetcher.close()


def test_size_failure_is_atomic_and_does_not_trigger_fallback(
    store: SqliteRegistry,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetcher = PoliteFetcher(
        store,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b"too many bytes"),
            )
        ),
    )

    def bad_fallback(*args):
        raise AssertionError("not a transport failure")

    monkeypatch.setattr(fetcher, "_curl", bad_fallback)
    try:
        result = fetcher.download("https://example.org/a", tmp_path / "output", max_bytes=2)
        assert not result.ok
        assert "max_download_bytes" in result.error
        assert not (tmp_path / "output").exists()
        assert not list(tmp_path.glob("*.tmp"))
    finally:
        fetcher.close()


def test_http_refusal_does_not_retry_with_other_transport(
    store: SqliteRegistry,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetcher = PoliteFetcher(
        store,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(403),
            )
        ),
    )

    def bad_fallback(*args):
        raise AssertionError("HTTP refusal must not trigger fallback")

    monkeypatch.setattr(fetcher, "_curl", bad_fallback)
    try:
        assert (
            fetcher.download("https://example.org/a", tmp_path / "out", max_bytes=20).http_status
            == 403
        )
    finally:
        fetcher.close()
