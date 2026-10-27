"""JSON command boundary for supplied classifiers and custom file processors."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def call_json(
    command: tuple[str, ...], request: dict[str, Any], *, cwd: Path, timeout: float
) -> Any:
    """Run an argument vector without a shell; return one JSON stdout value."""
    result = subprocess.run(
        command,
        input=json.dumps(request),
        text=True,
        capture_output=True,
        cwd=cwd,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise ValueError(f"command failed ({result.returncode}): {result.stderr[-2000:]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("command must emit exactly one JSON value on stdout") from error
