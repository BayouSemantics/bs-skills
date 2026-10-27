"""Validated collection configuration and pipeline records."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class WorkerGroup(Record):
    count: int = Field(gt=0)
    model: str = Field(min_length=1)


class Format(Record):
    """Accepted file formats and how to turn them into classifier units.

    Commands receive a JSON request on stdin and return a JSON object with a
    ``units`` list. Relative paths are resolved against the collection root.
    """

    name: str = Field(min_length=1)
    extensions: tuple[str, ...] = ()
    media_types: tuple[str, ...] = ()
    processor: Literal["pdf", "text", "html", "image", "file", "zip", "command"]
    command: tuple[str, ...] = ()

    @model_validator(mode="after")
    def valid_format(self) -> Format:
        if not self.extensions and not self.media_types:
            raise ValueError("each format needs extensions or media_types")
        if any(not e.startswith(".") or "/" in e or "\\" in e for e in self.extensions):
            raise ValueError("extensions must be suffixes such as .pdf or .wav")
        if (self.processor == "command") != bool(self.command):
            raise ValueError("only a command processor takes a nonempty command")
        return self


class Classifier(Record):
    kind: Literal["command", "tfidf"]
    version: str = Field(min_length=1)
    command: tuple[str, ...] = ()
    artifact: str | None = None
    # Include every local code/model file that determines the verdict.
    files: tuple[str, ...] = ()
    timeout_seconds: float = Field(default=300, gt=0, le=3600)
    threshold: float = Field(default=0.5, gt=0, lt=1)
    minimum_precision: float = Field(default=0.9, ge=0, le=1)
    minimum_recall: float = Field(default=0.8, ge=0, le=1)

    @model_validator(mode="after")
    def valid_classifier(self) -> Classifier:
        if self.kind == "command" and (not self.command or not self.files):
            raise ValueError("a command classifier needs command and files for identity checks")
        if self.kind == "tfidf" and (not self.artifact or self.command):
            raise ValueError("a tfidf classifier needs artifact and no command")
        return self


class CollectionConfig(Record):
    name: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str = Field(min_length=1)
    formats: tuple[Format, ...] = Field(min_length=1)
    classifier: Classifier
    workers: tuple[WorkerGroup, ...] = Field(min_length=1)
    required_phrase_groups: tuple[tuple[str, ...], ...] = ()
    blocked_terms: tuple[str, ...] = ()
    max_download_bytes: int = Field(default=100_000_000, gt=0)
    max_archive_bytes: int = Field(default=500_000_000, gt=0)
    max_archive_members: int = Field(default=500, gt=0)
    max_units: int = Field(default=1000, gt=0)
    dpi: int = Field(default=150, ge=36, le=600)
    min_interval_seconds: float = Field(default=1.0, ge=1)

    @model_validator(mode="after")
    def meaningful_strings(self) -> CollectionConfig:
        if not self.description.strip() or any(not w.model.strip() for w in self.workers):
            raise ValueError("description and worker models must be nonblank")
        if any(not g or any(not p.strip() for p in g) for g in self.required_phrase_groups):
            raise ValueError("required phrase groups must contain nonblank phrases")
        if any(not term.strip() for term in self.blocked_terms):
            raise ValueError("blocked_terms must be nonblank")
        names = [f.name for f in self.formats]
        if len(names) != len(set(names)):
            raise ValueError("format names must be unique")
        return self


class Unit(Record):
    """One independently classified page, text, image, or other asset."""

    id: str = Field(min_length=1)
    path: Path
    media_type: str
    text: str = ""
    page_number: int | None = Field(default=None, ge=1)


class Decision(Record):
    unit_id: str
    decision: Literal["accept", "reject"]
    score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)


class ResourceInput(Record):
    url: str
    score: float | None = Field(default=None, ge=0, le=100)
    kind: Literal["candidate", "retry"] = "candidate"
    published_at: str | None = None
    notes: str | None = None
