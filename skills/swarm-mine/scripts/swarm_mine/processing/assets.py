"""Configurable asset preparation."""

from __future__ import annotations

import mimetypes
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from swarm_mine.hashing import sha256_file
from swarm_mine.models import Format, Unit
from swarm_mine.processing.render import PdfPageRenderer
from swarm_mine.processing.text import extract_all_page_texts
from swarm_mine.subprocesses import call_json
from swarm_mine.workspace import Workspace


class HtmlText(HTMLParser):
    """Extract visible static text, excluding script and style contents."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def identify(path: Path, name: str, media_type: str | None, formats: tuple[Format, ...]) -> Format:
    """Match configured types, preferring actual PDF/ZIP/image signatures."""
    with path.open("rb") as handle:
        magic = handle.read(16)
    detected = None
    for prefix, kind in (
        (b"%PDF-", "application/pdf"),
        (b"PK\x03\x04", "application/zip"),
        (b"\x89PNG", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
    ):
        if magic.startswith(prefix):
            detected = kind
            break
    supplied = (media_type or "").split(";")[0].lower()
    mime = detected or supplied or mimetypes.guess_type(name)[0]
    suffix = Path(urlsplit(name).path).suffix.lower()
    for fmt in formats:
        if mime in fmt.media_types:
            return fmt
    for fmt in formats:
        if suffix in fmt.extensions:
            # Never treat a known conflicting type as a filename's claimed type.
            if detected and detected not in fmt.media_types:
                expected = mimetypes.guess_type("file" + suffix)[0]
                if expected != detected:
                    continue
            if supplied == "text/html" and fmt.processor not in ("html", "text", "command"):
                continue
            return fmt
    raise UnsupportedFormat(f"no configured format matches {mime or suffix or name}")


class UnsupportedFormat(ValueError):
    pass


class AssetPreparer:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace

    def prepare(self, path: Path, fmt: Format, output: Path) -> list[Unit]:
        output.mkdir(parents=True, exist_ok=True)
        config = self.workspace.config
        media_type = (fmt.media_types or (mimetypes.guess_type(path.name)[0],))[0]
        media_type = media_type or "application/octet-stream"
        if fmt.processor == "pdf":
            from swarm_mine.processing.document import page_count

            if page_count(path) > config.max_units:
                raise ValueError("PDF exceeds max_units")
            texts = extract_all_page_texts(path)
            pages = PdfPageRenderer(dpi=config.dpi).render_pages(path, output)
            return [
                Unit(
                    id=f"page-{p.page_number}",
                    path=p.path.resolve(),
                    media_type="image/png",
                    text=texts[p.page_number - 1],
                    page_number=p.page_number,
                )
                for p in pages
            ]
        if fmt.processor == "command":
            result = call_json(
                fmt.command,
                {
                    "asset": str(path.resolve()),
                    "format": fmt.name,
                    "output_dir": str(output.resolve()),
                    "target": config.description,
                },
                cwd=self.workspace.root,
                timeout=config.classifier.timeout_seconds,
            )
            units = [Unit.model_validate(item) for item in result["units"]]
            for unit in units:
                if not unit.path.is_absolute() or not unit.path.is_file():
                    raise ValueError("processor unit paths must be absolute existing files")
                if not unit.path.resolve().is_relative_to(output.resolve()):
                    raise ValueError("processor outputs must stay inside output_dir")
            return self._validate(units)
        if fmt.processor == "zip":
            raise ValueError("archives are processed by member")
        text = ""
        if fmt.processor in ("text", "html"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if fmt.processor == "html":
                parser = HtmlText()
                parser.feed(text)
                text = " ".join(parser.parts)
        return [Unit(id="asset", path=path.resolve(), media_type=media_type, text=text)]

    def _validate(self, units: list[Unit]) -> list[Unit]:
        if not units or len(units) > self.workspace.config.max_units:
            raise ValueError("processor must return 1..max_units units")
        if len({unit.id for unit in units}) != len(units):
            raise ValueError("processor unit ids must be unique")
        return units

    def extract(self, path: Path, output: Path) -> list[tuple[str, Path]]:
        """Extract flat hash-named members, bounding member count and total bytes."""
        output.mkdir(parents=True, exist_ok=True)
        config = self.workspace.config
        members = []
        written = 0
        with zipfile.ZipFile(path) as archive:
            infos = [i for i in archive.infolist() if not i.is_dir()]
            if len(infos) > config.max_archive_members:
                raise ValueError("archive exceeds max_archive_members")
            if sum(i.file_size for i in infos) > config.max_archive_bytes:
                raise ValueError("archive exceeds max_archive_bytes")
            for index, info in enumerate(infos):
                staging = output / f"member-{index}.tmp"
                with archive.open(info) as source, staging.open("wb") as target:
                    while chunk := source.read(256 * 1024):
                        written += len(chunk)
                        if written > config.max_archive_bytes:
                            raise ValueError("archive exceeds max_archive_bytes")
                        target.write(chunk)
                suffix = Path(info.filename).suffix.lower()
                destination = output / f"{sha256_file(staging)}{suffix}"
                staging.replace(destination)
                members.append((info.filename, destination))
        return members
