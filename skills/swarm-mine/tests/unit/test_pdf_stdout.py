from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pymupdf

SCRIPT = """
import sys
from pathlib import Path
from swarm_mine.processing.document import page_count
from swarm_mine.processing.render import PdfPageRenderer
from swarm_mine.processing.text import extract_all_page_texts, extract_page_text
pdf = Path(sys.argv[1])
page_count(pdf)
extract_page_text(pdf, 1)
extract_all_page_texts(pdf)
PdfPageRenderer(dpi=36).render_pages(pdf, pdf.parent / "pages")
"""


def test_pdf_processing_writes_nothing_to_stdout(tmp_path: Path) -> None:
    """CLI commands promise JSON-only stdout, so PDF helpers must stay silent."""
    document = pymupdf.open()
    document.new_page().insert_text((50, 50), "target")
    pdf = tmp_path / "a.pdf"
    document.save(pdf)
    document.close()
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(pdf)],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONPATH": str(scripts)},
    )
    assert result.stdout == ""
