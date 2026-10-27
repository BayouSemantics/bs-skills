"""Streamed atomic downloads."""

from __future__ import annotations

import subprocess
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict

from swarm_mine.store.sqlite import SqliteRegistry
from swarm_mine.urls import host_of

USER_AGENT = "bs-swarm-mine/0.1 (asset collection)"
REDIRECTS = {301, 302, 303, 307, 308}


class FetchOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)
    ok: bool
    http_status: int | None = None
    content_type: str | None = None
    byte_size: int | None = None
    error: str | None = None
    final_url: str


class Fetcher(Protocol):
    def download(self, url: str, destination: Path, *, max_bytes: int) -> FetchOutcome: ...

    def close(self) -> None: ...


class PoliteFetcher:
    """Share request leases across every local worker, including redirects.

    A transport fallback is attempted only on transport failure. HTTP refusals
    remain answers. Downloads use unique staging files and an atomic rename.
    """

    def __init__(
        self,
        store: SqliteRegistry,
        *,
        interval: float = 1,
        transport: str = "auto",
        client: httpx.Client | None = None,
    ) -> None:
        self.store = store
        self.interval = max(1, interval)
        self.transport = transport
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=60,
            follow_redirects=False,
        )

    def close(self) -> None:
        self.client.close()

    @contextmanager
    def _host(self, url: str) -> Iterator[None]:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username:
            raise ValueError("download URLs must be HTTP(S), without embedded credentials")
        host = host_of(url)
        interval = self.store.host_interval(host, self.interval)
        token = uuid.uuid4().hex
        deadline = time.monotonic() + 65
        while delay := self.store.acquire_host(host, token, interval=interval):
            if time.monotonic() >= deadline:
                raise TimeoutError("host is busy; retry on a later mining run")
            time.sleep(delay)
        try:
            yield
        finally:
            self.store.release_host(host, token, interval=interval)

    def download(self, url: str, destination: Path, *, max_bytes: int) -> FetchOutcome:
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.with_name(f".{destination.name}-{uuid.uuid4().hex}.tmp")
        current = url
        try:
            for _ in range(11):
                if self.transport == "curl-http1":
                    status, headers = self._curl(current, staging, max_bytes)
                else:
                    try:
                        status, headers = self._httpx(current, staging, max_bytes)
                    except httpx.TransportError:
                        if self.transport != "auto":
                            raise
                        staging.unlink(missing_ok=True)
                        status, headers = self._curl(current, staging, max_bytes)
                if status in REDIRECTS:
                    location = headers.get("location")
                    if not location:
                        raise ValueError("redirect has no Location header")
                    current = urljoin(current, location)
                    staging.unlink(missing_ok=True)
                    continue
                content_type = headers.get("content-type", "").split(";")[0].lower() or None
                if not 200 <= status < 300:
                    return FetchOutcome(
                        ok=False,
                        http_status=status,
                        final_url=current,
                        content_type=content_type,
                        error=f"HTTP {status}",
                    )
                size = staging.stat().st_size
                staging.replace(destination)
                return FetchOutcome(
                    ok=True,
                    http_status=status,
                    content_type=content_type,
                    byte_size=size,
                    final_url=current,
                )
            raise ValueError("too many redirects")
        except (OSError, ValueError, httpx.HTTPError, subprocess.SubprocessError) as error:
            return FetchOutcome(ok=False, final_url=current, error=str(error))
        finally:
            staging.unlink(missing_ok=True)

    def _httpx(self, url: str, staging: Path, max_bytes: int) -> tuple[int, dict[str, str]]:
        with self._host(url), self.client.stream("GET", url, follow_redirects=False) as response:
            headers = dict(response.headers)
            if not 200 <= response.status_code < 300:
                return response.status_code, headers
            deadline = time.monotonic() + 300
            size = 0
            with staging.open("wb") as handle:
                for chunk in response.iter_bytes(256 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("max_download_bytes exceeded")
                    if time.monotonic() > deadline:
                        raise TimeoutError("download exceeded 300 seconds")
                    handle.write(chunk)
            return response.status_code, headers

    def _curl(self, url: str, staging: Path, max_bytes: int) -> tuple[int, dict[str, str]]:
        header_path = staging.with_suffix(".headers")
        try:
            with self._host(url):
                result = subprocess.run(
                    [
                        "curl",
                        "--http1.1",
                        "--silent",
                        "--show-error",
                        "--max-time",
                        "60",
                        "--proto",
                        "=http,https",
                        "--user-agent",
                        USER_AGENT,
                        "--max-filesize",
                        str(max_bytes),
                        "--dump-header",
                        str(header_path),
                        "--output",
                        str(staging),
                        "--write-out",
                        "%{http_code}",
                        "--url",
                        url,
                    ],
                    capture_output=True,
                    check=False,
                    timeout=65,
                )
                if result.returncode:
                    raise OSError(result.stderr.decode(errors="replace").strip())
                if staging.stat().st_size > max_bytes:
                    raise ValueError("max_download_bytes exceeded")
                status = int(result.stdout.decode())
                # The final block follows any proxy CONNECT / 100 Continue response.
                block = header_path.read_text(errors="replace").strip().split("\n\n")[-1]
                headers = {}
                for line in block.splitlines()[1:]:
                    if ":" in line:
                        key, value = line.split(":", 1)
                        headers[key.lower()] = value.strip()
                return status, headers
        finally:
            header_path.unlink(missing_ok=True)
