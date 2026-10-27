"""Complete per-URL mining flow: claim, fetch, prepare, classify, retain, record."""

from __future__ import annotations

import json
import shutil
import threading
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from swarm_mine.classification import Classifier, check_classifier, make_classifier
from swarm_mine.fetch import Fetcher, PoliteFetcher
from swarm_mine.hashing import sha256_file
from swarm_mine.models import ResourceInput, Unit
from swarm_mine.processing.assets import AssetPreparer, UnsupportedFormat, identify
from swarm_mine.publishing import AssetPublisher
from swarm_mine.screening import screen
from swarm_mine.store.sqlite import SqliteRegistry
from swarm_mine.workspace import Workspace


class EventLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path

    def emit(self, event: str, **data: Any) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as handle:
                handle.write(
                    json.dumps({"ts": datetime.now(UTC).isoformat(), "event": event, **data}) + "\n"
                )


class MiningDriver:
    """One lazy classifier and one polite client per worker process."""

    def __init__(
        self,
        workspace: Workspace,
        store: SqliteRegistry,
        *,
        fetcher: Fetcher | None = None,
        classifier: Classifier | None = None,
        events: EventLog | None = None,
    ) -> None:
        self.workspace = workspace
        self.store = store
        store.bind("qualification_id", workspace.qualification_id)
        self.fetcher = fetcher or PoliteFetcher(
            store, interval=workspace.config.min_interval_seconds
        )
        self.classifier = classifier
        self.events = events or EventLog()
        self.preparer = AssetPreparer(workspace)
        self.publisher = AssetPublisher(workspace.assets)
        self.classifier_id = check_classifier(workspace)["classifier_id"]
        store.bind("classifier_id", self.classifier_id)

    @contextmanager
    def _lease(self, resource: dict[str, Any]) -> Iterator[None]:
        stop = threading.Event()

        def heartbeat() -> None:
            while not stop.wait(30):
                if not self.store.renew(resource["url_sha256"], resource["claim_token"]):
                    break

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=35)

    def run_url(self, url: str, *, source: str, agent: str) -> dict[str, Any]:
        self.store.add_resources(source, [ResourceInput(url=url)])
        existing = self.store.resource(url)
        if existing and existing["status"] != "unmined":
            return {"outcome": "skipped", "reason": existing["status"], "url": url}
        resource = self.store.claim(agent, source=source, url=url)
        if resource is None:
            return {"outcome": "skipped", "reason": "claim_refused", "url": url}
        return self.run_claimed(resource)

    def run_claimed(self, resource: dict[str, Any]) -> dict[str, Any]:
        url = resource["original_url"]
        job = self.workspace.work / "jobs" / resource["url_sha256"] / resource["claim_token"]
        job.mkdir(parents=True)
        document = job / "download"
        started = time.monotonic()
        self.events.emit("claimed", url=url, agent=resource["claimed_by"])
        try:
            with self._lease(resource):
                fetched = self.fetcher.download(
                    url,
                    document,
                    max_bytes=self.workspace.config.max_download_bytes,
                )
                self.events.emit("fetched", url=url, **fetched.model_dump())
                if not fetched.ok:
                    if fetched.http_status in (404, 410):
                        self.store.mark(url, "failed", fetched.error)
                        return {"outcome": "marked_failed", "url": url, "reason": fetched.error}
                    return {
                        "outcome": "skipped",
                        "url": url,
                        "reason": "fetch_transient",
                        "error": fetched.error,
                    }
                digest = sha256_file(document)
                known = self.store.covered_file(digest)
                if known:
                    if known["eligible"]:
                        self.publisher._verify(
                            self.workspace.assets / digest, digest, self.classifier_id
                        )
                    self.store.complete(resource, [], digest)
                    return {"outcome": "recorded_duplicate", "url": url, "content_sha256": digest}
                records = self._process(document, fetched.final_url, fetched.content_type, url, job)
                # Retained bytes are durable before the URL becomes covered.
                self.store.complete(resource, records, digest)
                result = records[-1]
                summary = {
                    "outcome": "retained" if result["eligible"] else "recorded_ineligible",
                    "url": url,
                    **result,
                    "duration_seconds": time.monotonic() - started,
                }
                self.events.emit("recorded", **summary)
                return summary
        finally:
            self.store.release(resource["claimed_by"], url)
            shutil.rmtree(job)

    def _record(self, path: Path, accepted: int, reason: str | None) -> dict[str, Any]:
        return {
            "content_sha256": sha256_file(path),
            "byte_size": path.stat().st_size,
            "eligible": accepted > 0,
            "accepted_units": accepted,
            "reason": reason,
            "classifier_id": self.classifier_id,
        }

    def _process(
        self,
        path: Path,
        name: str,
        media_type: str | None,
        url: str,
        job: Path,
    ) -> list[dict[str, Any]]:
        config = self.workspace.config
        try:
            fmt = identify(path, name, media_type, config.formats)
        except UnsupportedFormat:
            return [self._record(path, 0, "unsupported_format")]
        if fmt.processor != "zip":
            units = self.preparer.prepare(path, fmt, job / "units")
            reason = screen(
                units, url, blocked=config.blocked_terms, required=config.required_phrase_groups
            )
            return [self._qualify(path, units, reason, url, fmt.extensions, None)]

        members = self.preparer.extract(path, job / "members")
        prepared = []
        records = []
        seen = set()
        blocked = False
        total_units = 0
        for member_name, member in members:
            digest = sha256_file(member)
            if digest in seen:
                continue
            seen.add(digest)
            try:
                member_format = identify(member, member_name, None, config.formats)
            except UnsupportedFormat:
                continue
            if member_format.processor == "zip":
                continue
            units = self.preparer.prepare(member, member_format, job / "units" / digest)
            total_units += len(units)
            if total_units > config.max_units:
                raise ValueError("archive exceeds max_units")
            reason = screen(
                units, url, blocked=config.blocked_terms, required=config.required_phrase_groups
            )
            blocked = blocked or reason == "blocked"
            prepared.append((member, units, reason, member_format, member_name))
        if blocked:
            return [self._record(path, 0, "blocked")]
        accepted_hashes = []
        for member, units, reason, member_format, member_name in prepared:
            record = self._qualify(
                member, units, reason, url, member_format.extensions, member_name
            )
            records.append(record)
            if record["eligible"]:
                accepted_hashes.append(record["content_sha256"])
        count = sum(r["accepted_units"] for r in records)
        if count:
            self.publisher.publish(
                path,
                digest=sha256_file(path),
                suffix=".zip",
                url=url,
                classifier_id=self.classifier_id,
                units=[],
                decisions=[],
                members=accepted_hashes,
            )
        records.append(self._record(path, count, None if count else "no_accept_units"))
        return records

    def _qualify(
        self,
        path: Path,
        units: list[Unit],
        reason: str | None,
        url: str,
        extensions: tuple[str, ...],
        member_name: str | None,
    ) -> dict[str, Any]:
        if reason:
            return self._record(path, 0, reason)
        if self.classifier is None:
            self.classifier = make_classifier(self.workspace)
        decisions = self.classifier.classify(units)
        accepted = sum(d.decision == "accept" for d in decisions)
        self.events.emit("classified", url=url, member=member_name, accepted_units=accepted)
        if accepted:
            self.publisher.publish(
                path,
                digest=sha256_file(path),
                suffix=extensions[0] if extensions else ".bin",
                url=url,
                classifier_id=self.classifier_id,
                units=units,
                decisions=decisions,
                member_name=member_name,
            )
        return self._record(path, accepted, None if accepted else "no_accept_units")

    def run_pool(
        self,
        *,
        agent: str,
        source: str | None = None,
        limit: int | None = None,
        min_score: float | None = None,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        outcomes: Counter[str] = Counter()
        errors = 0
        processed = 0
        stopped = "pool_drained"
        while True:
            if limit is not None and processed >= limit:
                stopped = "limit"
                break
            if deadline is not None and time.monotonic() - started >= deadline:
                stopped = "deadline"
                break
            resource = self.store.claim(agent, source=source, min_score=min_score)
            if not resource:
                break
            try:
                summary = self.run_claimed(resource)
                outcomes[summary["outcome"]] += 1
                errors = errors + 1 if summary.get("reason") == "fetch_transient" else 0
                self.events.emit("url_summary", **summary)
            except Exception as error:
                outcomes["error"] += 1
                errors += 1
                self.events.emit("error", url=resource["original_url"], error=str(error))
            processed += 1
            if errors >= 3:
                stopped = "error_streak"
                break
        hints = {
            "pool_drained": "no host has free work; find and register more URLs; never poll",
            "limit": "budget spent; resume when you have more",
            "deadline": "budget spent; resume when you have more",
            "error_streak": "three consecutive failures; investigate before resuming",
        }
        return {
            "stopped": stopped,
            "hint": hints[stopped],
            "processed": processed,
            "outcomes": dict(outcomes),
        }
