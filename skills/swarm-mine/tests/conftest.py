from __future__ import annotations

import sys
from pathlib import Path

import pytest
from swarm_mine.models import CollectionConfig
from swarm_mine.store.sqlite import SqliteRegistry
from swarm_mine.workspace import Workspace

PREDICTOR = """import json, sys
request = json.load(sys.stdin)
print(json.dumps({"decisions": [{"unit_id": u["id"],
    "decision": "accept" if "target" in u["text"].lower() else "reject",
    "score": 0.9 if "target" in u["text"].lower() else 0.1,
    "reason": "fixture classifier"} for u in request["units"]]}))
"""


@pytest.fixture
def config() -> CollectionConfig:
    return CollectionConfig.model_validate(
        {
            "name": "test-collection",
            "description": "Documents containing the target",
            "workers": [{"count": 2, "model": "user-selected-model"}],
            "classifier": {
                "kind": "command",
                "version": "v1",
                "command": [sys.executable, "classifier/predict.py"],
                "files": ["classifier/predict.py"],
            },
            "formats": [
                {
                    "name": "text",
                    "extensions": [".txt"],
                    "media_types": ["text/plain"],
                    "processor": "text",
                },
                {
                    "name": "pdf",
                    "extensions": [".pdf"],
                    "media_types": ["application/pdf"],
                    "processor": "pdf",
                },
                {
                    "name": "zip",
                    "extensions": [".zip"],
                    "media_types": ["application/zip"],
                    "processor": "zip",
                },
            ],
        }
    )


@pytest.fixture
def workspace(tmp_path: Path, config: CollectionConfig) -> Workspace:
    workspace = Workspace.initialize(config, tmp_path / "collection with spaces")
    (workspace.root / "classifier/predict.py").write_text(PREDICTOR)
    return workspace


@pytest.fixture
def store(workspace: Workspace) -> SqliteRegistry:
    store = SqliteRegistry(workspace.database)
    store.initialize(workspace.qualification_id)
    store.source_add(
        "example.org",
        display_name="Example",
        rights_tier="public_record",
        access_urls=["https://example.org/"],
    )
    return store
