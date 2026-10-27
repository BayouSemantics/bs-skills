"""URL normalization for coverage-cache keys and registry source ids."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_LABEL = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
HOSTNAME_PATTERN = re.compile(rf"^{_LABEL}(?:\.{_LABEL})+$")
"""Two or more dot-separated labels, hyphens allowed inside them (RFC 1123).

Underscores are not hostname characters, which is what separates a real domain
from a themed id: ``plan-rooms.example.org`` is a host, ``plan_rooms`` is not.
"""


def normalize_url(url: str) -> str:
    """Return a canonical form of ``url`` used as the covered-URL key.

    Rules (intentionally small until the mining workflow needs more):

    * strip leading/trailing whitespace
    * lowercase scheme and host
    * drop the fragment (``#...``)
    * leave path, query, userinfo, and port as discovered

    Args:
        url: Raw discovered URL.

    Returns:
        Normalized URL string.
    """
    stripped = url.strip()
    parts = urlsplit(stripped)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    return urlunsplit((scheme, netloc, parts.path, parts.query, ""))


def host_of(url: str) -> str:
    """Return the lowercase hostname of ``url`` with ``www.`` dropped.

    Args:
        url: Absolute URL.

    Returns:
        Bare hostname.

    Raises:
        ValueError: When ``url`` carries no hostname.
    """
    host = (urlsplit(url.strip()).hostname or "").lower()
    if not host:
        raise ValueError(f"{url!r} has no hostname")
    return host.removeprefix("www.")


def source_id_for_host(host: str) -> str:
    """Return the registry id for a hostname.

    A source is a domain: leases, politeness, credentials, and exhaustion are
    all per-host properties, so the id *is* the host — lowercased with ``www.``
    dropped, and otherwise untransformed. Keeping it readable as a domain means
    a registry listing can be read as the map of hosts it actually is.

    Args:
        host: Hostname, with or without a ``www.`` prefix.

    Returns:
        Registry source id, e.g. ``documents.example.org``.

    Raises:
        ValueError: When ``host`` is not a dotted hostname.
    """
    bare = host.strip().lower().removeprefix("www.")
    if not HOSTNAME_PATTERN.match(bare):
        raise ValueError(f"{host!r} is not a hostname")
    return bare


def source_id_for_url(url: str) -> str:
    """Return the registry id for the host serving ``url``.

    Args:
        url: Absolute URL somewhere on the source.

    Returns:
        Registry source id.

    Raises:
        ValueError: When ``url`` carries no usable hostname.
    """
    return source_id_for_host(host_of(url))


__all__ = [
    "HOSTNAME_PATTERN",
    "host_of",
    "normalize_url",
    "source_id_for_host",
    "source_id_for_url",
]
