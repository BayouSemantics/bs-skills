"""Cheap PDF inspection helpers."""

from __future__ import annotations

from pathlib import Path


def page_count(pdf_path: Path) -> int:
    """Count the pages of a PDF.

    Args:
        pdf_path: Source PDF.

    Returns:
        Number of pages.
    """
    import fitz

    with fitz.open(pdf_path) as document:
        return int(document.page_count)


__all__ = ["page_count"]
