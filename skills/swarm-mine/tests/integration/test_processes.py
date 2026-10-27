from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from swarm_mine.models import ResourceInput
from swarm_mine.store.sqlite import SqliteRegistry
from swarm_mine.workspace import Workspace


def test_independent_processes_never_claim_the_same_resource(
    workspace: Workspace,
    store: SqliteRegistry,
) -> None:
    store.add_resources(
        "example.org", [ResourceInput(url=f"https://example.org/{i}") for i in range(30)]
    )
    script = """import json,sys
from pathlib import Path
from swarm_mine.store.sqlite import SqliteRegistry
store = SqliteRegistry(Path(sys.argv[1]))
claimed = []
while row := store.claim(sys.argv[2]):
    claimed.append(row["url_sha256"])
print(json.dumps(claimed))
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(workspace.database), str(i)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for i in range(6)
    ]
    claimed = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, stderr
        claimed.extend(json.loads(stdout))
    assert len(claimed) == len(set(claimed)) == 30


def test_real_downloads_from_two_processes_share_host_pacing(
    workspace: Workspace,
    store: SqliteRegistry,
    tmp_path: Path,
) -> None:
    starts, ends = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            starts.append(time.monotonic())
            time.sleep(0.1)
            body = b"target asset"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            ends.append(time.monotonic())

        def log_message(self, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    script = """import json,sys
from pathlib import Path
from swarm_mine.store.sqlite import SqliteRegistry
from swarm_mine.fetch import PoliteFetcher
client = PoliteFetcher(SqliteRegistry(Path(sys.argv[1])))
try:
    print(client.download(sys.argv[2], Path(sys.argv[3]), max_bytes=1000).model_dump_json())
finally:
    client.close()
"""
    processes = []
    try:
        for i in range(2):
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        script,
                        str(workspace.database),
                        f"http://127.0.0.1:{server.server_port}/file",
                        str(tmp_path / f"file-{i}"),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            assert process.returncode == 0, stderr
            assert json.loads(stdout)["ok"]
        assert len(starts) == len(ends) == 2
        assert starts[1] - ends[0] >= 0.95
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()
        server.shutdown()
        server.server_close()
        thread.join()
