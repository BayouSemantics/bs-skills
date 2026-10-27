"""Build a bounded TF-IDF/logistic-regression classifier from labeled examples."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Literal

from pydantic import Field

from swarm_mine.hashing import sha256_file, sha256_text
from swarm_mine.models import Record
from swarm_mine.screening import normalize
from swarm_mine.store.sqlite import SqliteRegistry
from swarm_mine.workspace import Workspace


class Seed(Record):
    text: str = Field(min_length=1)
    label: Literal["accept", "reject"]
    split: Literal["train", "validation"]
    group: str = Field(min_length=1)


def train_text(workspace: Workspace, examples: Path) -> dict:
    """Evaluate on user-labeled held-out groups; never fit on validation data."""
    import joblib
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import confusion_matrix, precision_score, recall_score
    from sklearn.pipeline import Pipeline

    config = workspace.config.classifier
    if config.kind != "tfidf":
        raise ValueError("train-text requires classifier.kind=tfidf")
    if workspace.database.exists() and SqliteRegistry(workspace.database).mining_started():
        raise ValueError("mining already started; train a changed classifier in a new collection")
    seeds = []
    for number, line in enumerate(examples.read_text().splitlines(), 1):
        if line.strip():
            try:
                seeds.append(Seed.model_validate_json(line))
            except ValueError as error:
                raise ValueError(f"{examples}:{number}: {error}") from error
    if len(seeds) > 100_000 or sum(len(s.text) for s in seeds) > 50_000_000:
        raise ValueError("seed dataset exceeds small-model training limits")
    hashes: dict[str, str] = {}
    groups: dict[str, str] = {}
    for seed in seeds:
        digest = sha256_text(normalize(seed.text))
        if digest in hashes:
            raise ValueError("duplicate seed text; remove duplicates before evaluating")
        hashes[digest] = seed.split
        if seed.group in groups and groups[seed.group] != seed.split:
            raise ValueError("a seed group crosses train/validation; split by original source")
        groups[seed.group] = seed.split
    training = [s for s in seeds if s.split == "train"]
    validation = [s for s in seeds if s.split == "validation"]
    for label in ("accept", "reject"):
        if sum(s.label == label for s in training) < 2 or not any(
            s.label == label for s in validation
        ):
            raise ValueError(
                "need >=2 training and >=1 held-out example per label; request more seeds"
            )
    model = Pipeline(
        [
            (
                "features",
                TfidfVectorizer(ngram_range=(1, 2), max_features=20_000, sublinear_tf=True),
            ),
            (
                "classifier",
                LogisticRegression(max_iter=500, class_weight="balanced", random_state=0),
            ),
        ]
    )
    model.fit([s.text for s in training], [int(s.label == "accept") for s in training])
    actual = [int(s.label == "accept") for s in validation]
    predicted = (
        model.predict_proba([s.text for s in validation])[:, 1] >= config.threshold
    ).astype(int)
    precision = float(precision_score(actual, predicted, zero_division=0))
    recall = float(recall_score(actual, predicted, zero_division=0))
    artifact = workspace.resolve(config.artifact or "")
    if not artifact.is_relative_to(workspace.root / "classifier"):
        raise ValueError("trained artifact must be inside the collection's classifier directory")
    artifact.parent.mkdir(parents=True, exist_ok=True)
    staging = artifact.with_name(f".{artifact.name}-{uuid.uuid4().hex}.tmp")
    try:
        joblib.dump(model, staging)
        os.replace(staging, artifact)
    finally:
        staging.unlink(missing_ok=True)
    report = {
        "qualification_id": workspace.qualification_id,
        "artifact_sha256": sha256_file(artifact),
        "training_examples": len(training),
        "validation_examples": len(validation),
        "precision": precision,
        "recall": recall,
        "confusion_matrix": confusion_matrix(actual, predicted, labels=[0, 1]).tolist(),
        "passed": precision >= config.minimum_precision and recall >= config.minimum_recall,
    }
    (workspace.root / "classifier" / "evaluation.json").write_text(json.dumps(report, indent=2))
    return report
