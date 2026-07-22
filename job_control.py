"""Loopback-only HTTP control surface for OpenClaw and operators."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from job_system import _event, _job_dict, _now, connect, submit


def _handler(token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "GameWikiControl/1"

        def _authorized(self) -> bool:
            if not token:
                return True
            return self.headers.get("Authorization") == f"Bearer {token}"

        def _json(self, status: int, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            size = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(size) or b"{}")

        def do_GET(self):  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path == "/health":
                self._json(200, {"status": "ok", "time": _now()})
                return
            if not self._authorized():
                self._json(403, {"error": "forbidden"})
                return
            with connect() as db:
                if path == "/jobs":
                    rows = db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 200").fetchall()
                    self._json(200, [_job_dict(row) for row in rows])
                    return
                if path.startswith("/jobs/"):
                    job_id = path.split("/", 2)[2]
                    row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
                    if row:
                        self._json(200, _job_dict(row))
                    else:
                        self._json(404, {"error": "job not found"})
                    return
            self._json(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if not self._authorized():
                self._json(403, {"error": "forbidden"})
                return
            path = urlparse(self.path).path.rstrip("/")
            try:
                payload = self._body()
                if path == "/jobs":
                    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as temp:
                        json.dump(payload, temp, ensure_ascii=False)
                        config_path = Path(temp.name)
                    try:
                        job_id = submit(config_path)
                    finally:
                        config_path.unlink(missing_ok=True)
                    self._json(201, {"jobId": job_id})
                    return
                parts = path.split("/")
                if len(parts) == 4 and parts[1] == "jobs" and parts[3] in {"retry", "cancel"}:
                    job_id, action = parts[2], parts[3]
                    with connect() as db:
                        row = db.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
                        if not row:
                            self._json(404, {"error": "job not found"})
                            return
                        if action == "retry":
                            db.execute("UPDATE jobs SET status='queued',available_at=?,cancel_requested=0,last_error=NULL,finished_at=NULL,result_json=NULL,updated_at=? WHERE id=?", (_now(), _now(), job_id))
                            _event(db, job_id, "job.retried")
                        else:
                            db.execute("UPDATE jobs SET cancel_requested=1,status=CASE WHEN status IN ('queued','retry_wait','needs_attention') THEN 'cancelled' ELSE status END,updated_at=? WHERE id=?", (_now(), job_id))
                            cancelled = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
                            _event(
                                db,
                                job_id,
                                "job.cancel_requested",
                                notify=bool(cancelled and cancelled["status"] == "cancelled"),
                                status=cancelled["status"] if cancelled else None,
                            )
                    self._json(200, {"jobId": job_id, "action": action})
                    return
                self._json(404, {"error": "not found"})
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})

        def log_message(self, *_args):
            return

    return Handler


def control_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gamewiki.py control-server")
    parser.add_argument("--host", default=os.environ.get("GAMEWIKI_CONTROL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("GAMEWIKI_CONTROL_PORT", "8787")))
    args = parser.parse_args(argv)
    token = os.environ.get("GAMEWIKI_CONTROL_TOKEN", "").strip()
    if args.host not in {"127.0.0.1", "::1", "localhost"} and not token:
        parser.error("GAMEWIKI_CONTROL_TOKEN is required outside loopback")
    server = ThreadingHTTPServer((args.host, args.port), _handler(token))
    print(f"Game Wiki control listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
