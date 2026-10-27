"""Contract for URL normalization and host-derived source ids."""

from __future__ import annotations

import pytest
from swarm_mine.urls import (
    host_of,
    normalize_url,
    source_id_for_host,
    source_id_for_url,
)


def test_normalize_lowercases_host_and_drops_the_fragment() -> None:
    assert normalize_url(" HTTPS://Example.com/a.pdf#page=2 ") == "https://example.com/a.pdf"


def test_host_drops_the_www_prefix() -> None:
    assert host_of("https://WWW.Example.com/search?q=target") == "example.com"


def test_host_rejects_a_url_without_one() -> None:
    with pytest.raises(ValueError):
        host_of("not-a-url")


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("documents.example.org", "documents.example.org"),
        ("www.DOCUMENTS.Example.org", "documents.example.org"),
        ("plan-rooms.example.org", "plan-rooms.example.org"),
        ("records.example.org", "records.example.org"),
    ],
)
def test_source_id_is_the_bare_hostname(host: str, expected: str) -> None:
    assert source_id_for_host(host) == expected


@pytest.mark.parametrize("host", ["localhost", "plan_rooms", "", "   ", "."])
def test_source_id_rejects_anything_that_is_not_a_domain(host: str) -> None:
    with pytest.raises(ValueError):
        source_id_for_host(host)


def test_source_id_from_a_deep_url() -> None:
    assert (
        source_id_for_url("https://records.example.org/wba/view?id=7#top") == "records.example.org"
    )
