from __future__ import annotations

import json
from pathlib import Path

import pytest
from swarm_mine.classification import TextClassifier, check_classifier
from swarm_mine.models import Classifier, CollectionConfig, Unit
from swarm_mine.store.sqlite import SqliteRegistry
from swarm_mine.training import train_text
from swarm_mine.workspace import Workspace


@pytest.fixture
def text_workspace(tmp_path: Path, config: CollectionConfig) -> Workspace:
    updated = config.model_copy(
        update={
            "classifier": Classifier(
                kind="tfidf",
                version="v1",
                artifact="classifier/model.joblib",
            )
        }
    )
    return Workspace.initialize(updated, tmp_path / "text-collection")


def examples(workspace: Workspace) -> tuple[Path, list[dict]]:
    rows = []
    for label, words in (
        ("accept", "target invoice payment amount total"),
        ("reject", "cooking recipes ingredients food oven"),
    ):
        for i in range(6):
            rows.append(
                {
                    "text": f"{words} document {label} {i}",
                    "label": label,
                    "split": "train" if i < 4 else "validation",
                    "group": f"{label}-{i}",
                }
            )
    path = workspace.root / "seeds/examples.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path, rows


def test_small_text_model_trains_evaluates_and_classifies(text_workspace: Workspace) -> None:
    path, _ = examples(text_workspace)
    report = train_text(text_workspace, path)
    assert report["passed"]
    assert report["training_examples"] == 8
    assert report["validation_examples"] == 4
    assert check_classifier(text_workspace)["ready"]
    result = TextClassifier(text_workspace).classify(
        [
            Unit(
                id="example",
                path=path,
                media_type="text/plain",
                text="target invoice payment amount total",
            )
        ]
    )
    assert result[0].decision == "accept"


@pytest.mark.parametrize("leak", ["text", "group"])
def test_training_rejects_data_leakage(text_workspace: Workspace, leak: str) -> None:
    path, rows = examples(text_workspace)
    rows[4][leak] = rows[0][leak]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError, match="duplicate|crosses"):
        train_text(text_workspace, path)
    assert not (text_workspace.root / "classifier/model.joblib").exists()


def test_training_requires_examples_of_both_classes(text_workspace: Workspace) -> None:
    path, rows = examples(text_workspace)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows if row["label"] == "accept"))
    with pytest.raises(ValueError, match="request more seeds"):
        train_text(text_workspace, path)


def test_retraining_is_allowed_during_setup_but_frozen_for_mining(
    text_workspace: Workspace,
) -> None:
    path, _ = examples(text_workspace)
    train_text(text_workspace, path)
    assert train_text(text_workspace, path)["passed"]
    store = SqliteRegistry(text_workspace.database)
    store.initialize(text_workspace.qualification_id)
    store.bind("classifier_id", text_workspace.classifier_id())
    with pytest.raises(ValueError, match="mining already started"):
        train_text(text_workspace, path)
