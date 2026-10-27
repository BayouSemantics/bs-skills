"""SQLite source registry and coverage cache.

Short BEGIN IMMEDIATE transactions protect claims across local processes.
Network requests and classification run outside database transactions.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from swarm_mine.hashing import sha256_text
from swarm_mine.models import ResourceInput
from swarm_mine.urls import normalize_url, source_id_for_url

SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS public_sources (
 source_id TEXT PRIMARY KEY, display_name TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('active','exploratory','exhausted','blocked')),
 priority INTEGER NOT NULL DEFAULT 100, rights_tier TEXT NOT NULL,
 min_interval_seconds REAL NOT NULL DEFAULT 1 CHECK(min_interval_seconds>=1),
 access_urls TEXT NOT NULL, access_notes TEXT NOT NULL DEFAULT '',
 discovery_state TEXT NOT NULL DEFAULT '{}',
 exhausted_at REAL, exhaustion_notes TEXT,
 created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS source_observations (
 id INTEGER PRIMARY KEY, source_id TEXT NOT NULL REFERENCES public_sources(source_id),
 agent TEXT NOT NULL, note TEXT NOT NULL, observed_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS covered_files (
 content_sha256 TEXT PRIMARY KEY, byte_size INTEGER NOT NULL,
 eligible INTEGER NOT NULL CHECK(eligible IN (0,1)),
 accepted_units INTEGER NOT NULL, reason TEXT, classifier_id TEXT NOT NULL,
 first_seen_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS covered_resources (
 url_sha256 TEXT PRIMARY KEY, normalized_url TEXT NOT NULL UNIQUE,
 original_url TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES public_sources(source_id),
 status TEXT NOT NULL CHECK(status IN ('unmined','covered','failed','excluded')),
 kind TEXT NOT NULL CHECK(kind IN ('candidate','retry')),
 score REAL CHECK(score BETWEEN 0 AND 100), published_at REAL, notes TEXT,
 content_sha256 TEXT REFERENCES covered_files(content_sha256),
 claimed_by TEXT, claim_token TEXT, claim_expires_at REAL,
 first_seen_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS resource_queue ON covered_resources(source_id,status,score);
CREATE TABLE IF NOT EXISTS hosts (
 host TEXT PRIMARY KEY, next_fetch_allowed_at REAL NOT NULL DEFAULT 0,
 token TEXT, expires_at REAL
);
"""


class SqliteRegistry:
    """Each operation owns its connection, allowing threads and child processes."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except BaseException:
            if write:
                connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self, qualification_id: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError(f"unsupported registry schema version: {version}")
            conn.executescript(SCHEMA)
            conn.execute("PRAGMA user_version=1")
        self.bind("qualification_id", qualification_id)

    def bind(self, key: str, value: str) -> None:
        with self.connection(write=True) as conn:
            conn.execute("INSERT OR IGNORE INTO metadata VALUES (?,?)", (key, value))
            existing = conn.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()[0]
            if existing != value:
                raise ValueError(f"{key} changed; use a new collection for different qualification")

    def source_add(
        self,
        source_id: str,
        *,
        display_name: str,
        rights_tier: str,
        access_urls: Sequence[str],
        access_notes: str = "",
        status: str = "exploratory",
        priority: int = 100,
        min_interval_seconds: float = 1,
    ) -> None:
        expected = {source_id_for_url(url) for url in access_urls}
        if not access_urls or expected != {source_id}:
            raise ValueError(f"source id must equal the access URL hostname: {sorted(expected)}")
        now = time.time()
        with self.connection(write=True) as conn:
            if conn.execute(
                "SELECT 1 FROM public_sources WHERE source_id=?", (source_id,)
            ).fetchone():
                raise ValueError("source exists; curate it with source update")
            conn.execute(
                "INSERT INTO public_sources "
                "(source_id,display_name,status,priority,rights_tier,access_urls,access_notes,"
                "created_at,updated_at,min_interval_seconds) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    source_id,
                    display_name,
                    status,
                    priority,
                    rights_tier,
                    json.dumps(list(access_urls)),
                    access_notes,
                    now,
                    now,
                    min_interval_seconds,
                ),
            )

    def sources(self, source_id: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM public_sources WHERE (? IS NULL OR source_id=?) "
                "ORDER BY priority,source_id",
                (source_id, source_id),
            ).fetchall()
        result = [dict(row) for row in rows]
        for row in result:
            row["access_urls"] = json.loads(row["access_urls"])
            row["discovery_state"] = json.loads(row["discovery_state"])
        return result

    def source_update(self, source_id: str, **changes: Any) -> None:
        allowed = {
            "status",
            "priority",
            "discovery_state",
            "access_notes",
            "exhaustion_notes",
            "min_interval_seconds",
        }
        if set(changes) - allowed:
            raise ValueError("unsupported source fields")
        if "discovery_state" in changes:
            if not isinstance(changes["discovery_state"], dict):
                raise ValueError("discovery_state must be a JSON object")
            changes["discovery_state"] = json.dumps(changes["discovery_state"])
        if "status" in changes:
            changes["exhausted_at"] = time.time() if changes["status"] == "exhausted" else None
        changes["updated_at"] = time.time()
        with self.connection(write=True) as conn:
            assignments = ",".join(f"{key}=?" for key in changes)
            result = conn.execute(
                f"UPDATE public_sources SET {assignments} WHERE source_id=?",
                (*changes.values(), source_id),
            )
            if not result.rowcount:
                raise ValueError("unknown source; register it first")

    def log(self, source_id: str, agent: str, note: str) -> None:
        if not agent.strip() or not note.strip():
            raise ValueError("agent and note must be nonblank")
        with self.connection(write=True) as conn:
            conn.execute(
                "INSERT INTO source_observations (source_id,agent,note,observed_at) "
                "VALUES (?,?,?,?)",
                (source_id, agent, note, time.time()),
            )

    def observations(self, source_id: str) -> list[dict[str, Any]]:
        with self.connection() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM source_observations WHERE source_id=? "
                    "ORDER BY id DESC LIMIT 100",
                    (source_id,),
                )
            ]

    def add_resources(self, source_id: str, resources: Sequence[ResourceInput]) -> int:
        rows = []
        now = time.time()
        for resource in resources:
            if source_id_for_url(resource.url) != source_id:
                raise ValueError(f"URL host differs from source {source_id}: {resource.url}")
            normalized = normalize_url(resource.url)
            published = None
            if resource.published_at:
                date = datetime.fromisoformat(resource.published_at.replace("Z", "+00:00"))
                if date.tzinfo is None:
                    raise ValueError("published_at must include a timezone")
                published = date.astimezone(UTC).timestamp()
            rows.append(
                (
                    sha256_text(normalized),
                    normalized,
                    resource.url,
                    source_id,
                    resource.kind,
                    resource.score,
                    published,
                    resource.notes,
                    now,
                    now,
                )
            )
        with self.connection(write=True) as conn:
            if not conn.execute(
                "SELECT 1 FROM public_sources WHERE source_id=?", (source_id,)
            ).fetchone():
                raise ValueError("unknown source; register it first with source add")
            before = conn.total_changes
            conn.executemany(
                "INSERT OR IGNORE INTO covered_resources "
                "(url_sha256,normalized_url,original_url,source_id,status,kind,score,published_at,"
                "notes,first_seen_at,updated_at) VALUES (?,?,?,?,'unmined',?,?,?,?,?,?)",
                rows,
            )
            return conn.total_changes - before

    def resource(self, url: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM covered_resources WHERE url_sha256=?",
                (sha256_text(normalize_url(url)),),
            ).fetchone()
            return dict(row) if row else None

    def claim(
        self,
        agent: str,
        *,
        source: str | None = None,
        url: str | None = None,
        min_score: float | None = None,
        ttl_seconds: float = 3600,
    ) -> dict[str, Any] | None:
        if not agent.strip() or ttl_seconds <= 0:
            raise ValueError("agent and positive lease duration required")
        now = time.time()
        with self.connection(write=True) as conn:
            row = conn.execute(
                "SELECT r.* FROM covered_resources r JOIN public_sources s USING(source_id) "
                "LEFT JOIN hosts h ON h.host=r.source_id "
                "WHERE r.status='unmined' AND (r.claimed_by IS NULL OR r.claim_expires_at<=?) "
                "AND s.status IN ('active','exploratory') "
                "AND (? IS NULL OR r.source_id=?) AND (? IS NULL OR r.normalized_url=?) "
                "AND (? IS NULL OR r.score>=?) "
                "AND (h.token IS NULL OR h.expires_at<=?) "
                "AND (h.next_fetch_allowed_at IS NULL OR h.next_fetch_allowed_at<=?) "
                "ORDER BY s.priority,r.score DESC,r.published_at DESC,r.url_sha256 LIMIT 1",
                (
                    now,
                    source,
                    source,
                    normalize_url(url) if url else None,
                    normalize_url(url) if url else None,
                    min_score,
                    min_score,
                    now,
                    now,
                ),
            ).fetchone()
            if not row:
                return None
            token = uuid.uuid4().hex
            conn.execute(
                "UPDATE covered_resources SET claimed_by=?,claim_token=?,claim_expires_at=?,"
                "updated_at=? WHERE url_sha256=?",
                (agent, token, now + ttl_seconds, now, row["url_sha256"]),
            )
            return dict(row) | {
                "claimed_by": agent,
                "claim_token": token,
                "claim_expires_at": now + ttl_seconds,
            }

    def renew(self, key: str, token: str) -> bool:
        now = time.time()
        with self.connection(write=True) as conn:
            return bool(
                conn.execute(
                    "UPDATE covered_resources SET claim_expires_at=? WHERE url_sha256=? "
                    "AND claim_token=? AND status='unmined' AND claim_expires_at>?",
                    (now + 3600, key, token, now),
                ).rowcount
            )

    def release(self, agent: str, url: str | None = None) -> int:
        with self.connection(write=True) as conn:
            return conn.execute(
                "UPDATE covered_resources SET claimed_by=NULL,claim_token=NULL,"
                "claim_expires_at=NULL WHERE claimed_by=? AND status='unmined' "
                "AND (? IS NULL OR normalized_url=?)",
                (agent, url, normalize_url(url) if url else None),
            ).rowcount

    def mark(self, url: str, resolution: str, notes: str | None = None) -> bool:
        if resolution not in ("failed", "excluded"):
            raise ValueError("resolution must be failed or excluded")
        with self.connection(write=True) as conn:
            return bool(
                conn.execute(
                    "UPDATE covered_resources SET status=?,notes=COALESCE(?,notes),claimed_by=NULL,"
                    "claim_token=NULL,claim_expires_at=NULL,updated_at=? "
                    "WHERE normalized_url=? AND status<>'covered'",
                    (resolution, notes, time.time(), normalize_url(url)),
                ).rowcount
            )

    def covered_file(self, digest: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM covered_files WHERE content_sha256=?", (digest,)
            ).fetchone()
            return dict(row) if row else None

    def complete(
        self, resource: dict[str, Any], files: Sequence[dict[str, Any]], digest: str
    ) -> None:
        """Record files and URL together, only while this worker still owns the lease."""
        now = time.time()
        with self.connection(write=True) as conn:
            owned = conn.execute(
                "SELECT 1 FROM covered_resources WHERE url_sha256=? AND claim_token=? "
                "AND status='unmined' AND claim_expires_at>?",
                (resource["url_sha256"], resource["claim_token"], now),
            ).fetchone()
            if not owned:
                raise ValueError("URL lease lost; coverage was not recorded")
            for file in files:
                conn.execute(
                    "INSERT OR IGNORE INTO covered_files VALUES (?,?,?,?,?,?,?)",
                    (
                        file["content_sha256"],
                        file["byte_size"],
                        int(file["eligible"]),
                        file["accepted_units"],
                        file.get("reason"),
                        file["classifier_id"],
                        now,
                    ),
                )
            conn.execute(
                "UPDATE covered_resources SET status='covered',content_sha256=?,claimed_by=NULL,"
                "claim_token=NULL,claim_expires_at=NULL,updated_at=? WHERE url_sha256=?",
                (digest, now, resource["url_sha256"]),
            )

    def list_resources(
        self,
        *,
        source: str | None = None,
        status: str | None = None,
        url_like: str | None = None,
        notes_like: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        def pattern(value: str | None) -> str | None:
            if value is None:
                return None
            return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"

        url_pattern, notes_pattern = pattern(url_like), pattern(notes_like)
        with self.connection() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM covered_resources WHERE (? IS NULL OR source_id=?) "
                    "AND (? IS NULL OR status=?) "
                    "AND (? IS NULL OR normalized_url LIKE ? ESCAPE '\\') "
                    "AND (? IS NULL OR notes LIKE ? ESCAPE '\\') "
                    "ORDER BY updated_at DESC,url_sha256 LIMIT ?",
                    (
                        source,
                        source,
                        status,
                        status,
                        url_pattern,
                        url_pattern,
                        notes_pattern,
                        notes_pattern,
                        limit,
                    ),
                )
            ]

    def stats(self, since: float = 0) -> dict[str, Any]:
        with self.connection() as conn:
            queue = [
                dict(r)
                for r in conn.execute(
                    "SELECT source_id,status,COUNT(*) AS count FROM covered_resources "
                    "GROUP BY source_id,status ORDER BY source_id,status"
                )
            ]
            coverage = [
                dict(r)
                for r in conn.execute(
                    "SELECT x.source_id,COUNT(*) AS documents,"
                    "SUM(f.eligible) AS eligible_documents,"
                    "SUM(f.accepted_units) AS accepted_units FROM "
                    "(SELECT DISTINCT source_id,content_sha256 FROM covered_resources "
                    "WHERE status='covered') x JOIN covered_files f USING(content_sha256) "
                    "WHERE f.first_seen_at>=? GROUP BY x.source_id ORDER BY x.source_id",
                    (since,),
                )
            ]
            return {"resources": queue, "coverage": coverage}

    def active_claim_tokens(self) -> set[str]:
        with self.connection() as conn:
            return {
                row[0]
                for row in conn.execute(
                    "SELECT claim_token FROM covered_resources WHERE claim_expires_at>? "
                    "AND status='unmined'",
                    (time.time(),),
                )
            }

    def retained_hashes(self) -> set[str]:
        with self.connection() as conn:
            return {
                row[0]
                for row in conn.execute(
                    "SELECT content_sha256 FROM covered_files WHERE eligible=1",
                )
            }

    def mining_started(self) -> bool:
        """Whether a worker has frozen the classifier identity for mining."""
        with self.connection() as conn:
            return (
                conn.execute("SELECT 1 FROM metadata WHERE key='classifier_id'").fetchone()
                is not None
            )

    def host_interval(self, host: str, minimum: float) -> float:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT min_interval_seconds FROM public_sources WHERE source_id=?", (host,)
            ).fetchone()
            return max(minimum, row[0] if row else 1)

    def acquire_host(self, host: str, token: str, *, interval: float) -> float:
        """Return zero on acquisition or a bounded delay before retrying."""
        now = time.time()
        with self.connection(write=True) as conn:
            conn.execute("INSERT OR IGNORE INTO hosts(host) VALUES (?)", (host,))
            row = conn.execute("SELECT * FROM hosts WHERE host=?", (host,)).fetchone()
            if row["token"] and row["expires_at"] > now:
                return min(1.0, row["expires_at"] - now)
            if row["next_fetch_allowed_at"] > now:
                return min(1.0, row["next_fetch_allowed_at"] - now)
            conn.execute(
                "UPDATE hosts SET token=?,expires_at=?,next_fetch_allowed_at=? WHERE host=?",
                (token, now + 600, now + interval, host),
            )
            return 0

    def release_host(self, host: str, token: str, *, interval: float) -> None:
        with self.connection(write=True) as conn:
            conn.execute(
                "UPDATE hosts SET token=NULL,expires_at=NULL,next_fetch_allowed_at=? "
                "WHERE host=? AND token=?",
                (time.time() + interval, host, token),
            )
