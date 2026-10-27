"""Content and URL hashing for the asset mining pipeline."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Return the lowercase hex SHA-256 digest of a file's bytes.

    Args:
        path: Path to the file to hash.

    Returns:
        64-character lowercase hex digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    """Return the lowercase hex SHA-256 digest of UTF-8-encoded text.

    Args:
        text: String to hash (e.g. a normalized URL).

    Returns:
        64-character lowercase hex digest.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = ["sha256_file", "sha256_text"]
