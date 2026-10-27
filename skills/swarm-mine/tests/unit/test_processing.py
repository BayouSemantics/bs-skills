from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from swarm_mine.models import Unit
from swarm_mine.processing.assets import AssetPreparer, HtmlText, UnsupportedFormat, identify
from swarm_mine.screening import screen
from swarm_mine.workspace import Workspace


def test_phrase_groups_must_match_within_same_unit(tmp_path: Path) -> None:
    units = [
        Unit(id=str(i), path=tmp_path, media_type="text/plain", text=t)
        for i, t in enumerate(["target", "invoice"])
    ]
    assert (
        screen(units, "", blocked=(), required=(("target",), ("invoice",)))
        == "missing_required_phrase"
    )
    assert screen(units, "", blocked=(), required=()) is None
    assert screen(units, "https://blocked.org", blocked=("blocked",), required=()) == "blocked"


def test_html_excludes_script_and_style() -> None:
    parser = HtmlText()
    parser.feed("<style>unwanted</style><script>bad()</script><p>Target &amp; text</p>")
    assert " ".join(parser.parts) == "Target & text"


def test_format_configuration_does_not_accept_html_as_a_pdf(workspace: Workspace) -> None:
    path = workspace.work / "response"
    path.write_text("<html>Login</html>")
    with pytest.raises(UnsupportedFormat):
        identify(path, "https://example.org/file.pdf", "text/html", workspace.config.formats)


def test_archive_flattens_names_and_enforces_expansion_limit(workspace: Workspace) -> None:
    archive = workspace.work / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../../outside.txt", "target")
    members = AssetPreparer(workspace).extract(archive, workspace.work / "extracted")
    assert members[0][0] == "../../outside.txt"
    assert members[0][1].parent == workspace.work / "extracted"
    workspace.config = workspace.config.model_copy(update={"max_archive_bytes": 1})
    with pytest.raises(ValueError, match="max_archive_bytes"):
        AssetPreparer(workspace).extract(archive, workspace.work / "bounded")
