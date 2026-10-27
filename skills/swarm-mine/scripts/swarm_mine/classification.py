"""Local classifier interface and optional small text model."""

from __future__ import annotations

import json
from typing import Any, Protocol

from swarm_mine.models import Decision, Unit
from swarm_mine.subprocesses import call_json
from swarm_mine.workspace import Workspace


class Classifier(Protocol):
    def classify(self, units: list[Unit]) -> list[Decision]: ...


class CommandClassifier:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace

    def classify(self, units: list[Unit]) -> list[Decision]:
        config = self.workspace.config.classifier
        response = call_json(
            config.command,
            {
                "target": self.workspace.config.description,
                "units": [unit.model_dump(mode="json") for unit in units],
            },
            cwd=self.workspace.root,
            timeout=config.timeout_seconds,
        )
        decisions = [Decision.model_validate(row) for row in response["decisions"]]
        expected = {unit.id for unit in units}
        actual = [decision.unit_id for decision in decisions]
        if len(actual) != len(expected) or set(actual) != expected:
            raise ValueError("classifier must return exactly one decision for every input unit")
        return decisions


class TextClassifier:
    def __init__(self, workspace: Workspace) -> None:
        import joblib

        self.config = workspace.config.classifier
        self.model = joblib.load(workspace.resolve(self.config.artifact or ""))

    def classify(self, units: list[Unit]) -> list[Decision]:
        if any(not unit.text.strip() for unit in units):
            raise ValueError(
                "text classifier requires text for every unit; configure another processor"
            )
        probabilities = self.model.predict_proba([unit.text for unit in units])
        positive_index = list(self.model.classes_).index(1)
        return [
            Decision(
                unit_id=unit.id,
                score=float(row[positive_index]),
                decision="accept" if row[positive_index] >= self.config.threshold else "reject",
                reason=f"TF-IDF logistic regression; threshold={self.config.threshold}",
            )
            for unit, row in zip(units, probabilities, strict=True)
        ]


def make_classifier(workspace: Workspace) -> Classifier:
    if workspace.config.classifier.kind == "command":
        return CommandClassifier(workspace)
    return TextClassifier(workspace)


def check_classifier(workspace: Workspace) -> dict[str, Any]:
    """Check local files and held-out evaluation before allowing mining."""
    identity = workspace.classifier_id()
    if workspace.config.classifier.kind == "tfidf":
        report_path = workspace.root / "classifier" / "evaluation.json"
        report = json.loads(report_path.read_text())
        from swarm_mine.hashing import sha256_file

        config = workspace.config.classifier
        if report["artifact_sha256"] != sha256_file(workspace.resolve(config.artifact or "")):
            raise ValueError("evaluation does not describe the current classifier artifact")
        if report["qualification_id"] != workspace.qualification_id:
            raise ValueError("evaluation belongs to different qualification configuration")
        if not report["passed"]:
            raise ValueError("held-out evaluation failed; request better examples before mining")
    return {"ready": True, "classifier_id": identity}
