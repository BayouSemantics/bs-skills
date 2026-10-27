from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from swarm_mine.cli import main
from swarm_mine.store.sqlite import SqliteRegistry
from swarm_mine.workspace import Workspace


def test_script_preserves_notes_and_workspace_paths_without_shell_evaluation(
    workspace: Workspace,
    store: SqliteRegistry,
    tmp_path: Path,
) -> None:
    marker = tmp_path / "should-not-exist"
    note = f'quoted "note"; $(touch {marker}) `touch {marker}`'
    skill = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(skill / "scripts/mine.py"),
            "--workspace",
            str(workspace.root),
            "resource",
            "add",
            "--source",
            "example.org",
            "--url",
            "https://example.org/a.txt",
            "--score",
            "75",
            "--notes",
            note,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["inserted"] == 1
    assert store.resource("https://example.org/a.txt")["notes"] == note
    assert not marker.exists()


def test_cli_jsonl_resolves_relative_to_collection_and_rejects_invalid_batch(
    workspace: Workspace,
    store: SqliteRegistry,
    capsys,
) -> None:
    path = workspace.work / "scratch/urls.jsonl"
    path.write_text(
        '{"url":"https://example.org/a", "score":90}\n'
        '{"url":"https://example.org/b", "score":101}\n'
    )
    code = main(
        [
            "--workspace",
            str(workspace.root),
            "resource",
            "add",
            "--source",
            "example.org",
            "--jsonl",
            "work/scratch/urls.jsonl",
        ]
    )
    assert code == 1
    assert ":2:" in json.loads(capsys.readouterr().out)["error"]
    assert store.list_resources() == []


def test_cli_runs_from_an_unrelated_directory(
    workspace: Workspace, store: SqliteRegistry, tmp_path: Path
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts/mine.py"),
            "--workspace",
            str(workspace.root),
            "stats",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {"resources": [], "coverage": []}
