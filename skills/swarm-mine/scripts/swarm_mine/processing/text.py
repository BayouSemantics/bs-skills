"""Vector text extraction from PDF pages.

Only the embedded (vector) text layer is read — no OCR. Scanned documents
without a text layer yield empty strings.
"""

from __future__ import annotations

from pathlib import Path


def normalize_text(text: str) -> str:
    """Collapse all whitespace (including form feeds) to single spaces.

    Args:
        text: Raw extracted page text.

    Returns:
        Whitespace-normalized text.
    """
    return " ".join(text.replace("\f", " ").split())


def extract_page_text(pdf_path: Path, page_number: int) -> str:
    """Extract the vector text layer of one page.

    Args:
        pdf_path: Source PDF.
        page_number: 1-based page number.

    Returns:
        Normalized page text; empty string when the page has no text layer.
    """
    import fitz

    with fitz.open(pdf_path) as document:
        page = document.load_page(page_number - 1)
        return normalize_text(page.get_text())


def extract_all_page_texts(pdf_path: Path) -> list[str]:
    """Extract vector text for every page in one pass.

    Args:
        pdf_path: Source PDF.

    Returns:
        Normalized text per page, in 1-based page order.
    """
    import fitz

    with fitz.open(pdf_path) as document:
        return [normalize_text(page.get_text()) for page in document]


__all__ = ["extract_all_page_texts", "extract_page_text", "normalize_text"]
