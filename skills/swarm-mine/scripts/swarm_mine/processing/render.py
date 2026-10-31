"""Rasterize PDF pages into content-hash-named PNG files.

Pages land on disk as ``{image_sha256}.png``, so a page image's filename stem
*is* its identity: it joins directly to classifier unit identity computed from the same PNG bytes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class PageRender(BaseModel):
    """One page rendered to disk as a hash-named PNG."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page_number: int
    """1-based page number in the source document."""

    path: Path
    image_sha256: str
    width_px: int
    height_px: int
    dpi: int


class PdfPageRenderer:
    """Split a PDF into per-page PNG files named by content hash.

    Args:
        dpi: Raster resolution applied to every page.
    """

    def __init__(self, *, dpi: int = 200) -> None:
        self._dpi = dpi

    def render_pages(self, pdf_path: Path, out_dir: Path) -> list[PageRender]:
        """Render every page of a PDF into a directory.

        Each page is written as ``{sha256(png_bytes)}.png``. Rendering is
        deterministic for a given document and DPI, so re-running overwrites
        the same files and the operation is idempotent.

        Args:
            pdf_path: Source PDF.
            out_dir: Destination directory; created if missing.

        Returns:
            One :class:`PageRender` per page, in 1-based page order.
        """
        import pymupdf

        out_dir.mkdir(parents=True, exist_ok=True)
        zoom = self._dpi / 72.0
        renders: list[PageRender] = []
        with pymupdf.open(pdf_path) as document:
            for index, page in enumerate(document):
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                png_bytes = pixmap.tobytes("png")
                image_sha256 = hashlib.sha256(png_bytes).hexdigest()
                path = out_dir / f"{image_sha256}.png"
                path.write_bytes(png_bytes)
                renders.append(
                    PageRender(
                        page_number=index + 1,
                        path=path,
                        image_sha256=image_sha256,
                        width_px=pixmap.width,
                        height_px=pixmap.height,
                        dpi=self._dpi,
                    )
                )
        return renders


__all__ = ["PageRender", "PdfPageRenderer"]
