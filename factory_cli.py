"""Production supervisor and observability commands for the Game Wiki Factory."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from orchestrate_wiki import read_json, slugify, write_json


ROOT = Path(__file__).resolve().parent
PROJECTS_ROOT = ROOT.parent
RUNTIME_ROOT = ROOT / ".gamewiki" / "runs"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class PermitState:
    def __init__(self, llm_limit: int, per_key_limit: int, build_limit: int):
        self.limits = {"llm": llm_limit, "build": build_limit}
        self.per_key_limit = per_key_limit
        self.in_use: dict[str, int] = {}
        self.leases: dict[str, list[str]] = {}
        self.condition = threading.Condition()

    def limit(self, resource: str) -> int:
        return self.per_key_limit if resource.startswith("llm-key-") else self.limits.get(resource, 1)

    def acquire(self, resources: list[str]) -> str:
        resources = sorted(set(resources))
        with self.condition:
            self.condition.wait_for(lambda: all(self.in_use.get(r, 0) < self.limit(r) for r in resources))
            for resource in resources:
                self.in_use[resource] = self.in_use.get(resource, 0) + 1
            lease = uuid.uuid4().hex
            self.leases[lease] = resources
            return lease

    def release(self, lease: str) -> None:
        with self.condition:
            for resource in self.leases.pop(lease, []):
                self.in_use[resource] = max(0, self.in_use.get(resource, 0) - 1)
            self.condition.notify_all()


def _handler(state: PermitState, token: str):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            if self.headers.get("Authorization") != f"Bearer {token}":
                self.send_error(403)
                return
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if urlparse(self.path).path == "/acquire":
                result = {"lease": state.acquire([str(item) for item in payload.get("resources", [])])}
            elif urlparse(self.path).path == "/release":
                state.release(str(payload.get("lease", "")))
                result = {"released": True}
            else:
                self.send_error(404)
                return
            body = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    return Handler


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_child(game: str, env: dict[str, str], log_path: Path, passthrough: list[str]) -> dict:
    started = _now()
    command = [sys.executable, str(ROOT / "gamewiki.py"), game, *passthrough]
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            log.flush()
            print(f"[{slugify(game)}] {line}", end="", flush=True)
        code = process.wait()
    return {"game": game, "slug": slugify(game), "status": "complete" if code == 0 else "failed", "exitCode": code, "startedAt": started, "finishedAt": _now(), "log": str(log_path)}


def run_many(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="gamewiki.py run-many")
    parser.add_argument("games", nargs="*")
    parser.add_argument("--games-file", type=Path)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--llm-concurrency", type=int, default=6)
    parser.add_argument("--llm-per-key", type=int, default=2)
    parser.add_argument("--build-concurrency", type=int, default=1)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    games = list(args.games)
    if args.games_file:
        games.extend(line.strip() for line in args.games_file.read_text(encoding="utf-8-sig").splitlines() if line.strip() and not line.lstrip().startswith("#"))
    games = list(dict.fromkeys(games))
    if not games:
        parser.error("provide at least one game or --games-file")
    if args.jobs < 1 or args.llm_concurrency < 1 or args.llm_per_key < 1 or args.build_concurrency < 1:
        parser.error("all concurrency values must be positive")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
    run_dir = RUNTIME_ROOT / run_id
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    state = PermitState(args.llm_concurrency, args.llm_per_key, args.build_concurrency)
    token = secrets.token_urlsafe(24)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state, token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    manifest_path = run_dir / "manifest.json"
    manifest = {"schemaVersion": 1, "runId": run_id, "status": "running", "startedAt": _now(), "games": games, "results": []}
    write_json(manifest_path, manifest)
    events_path = run_dir / "events.jsonl"
    events_path.write_text(json.dumps({"event": "run.started", "at": manifest["startedAt"], "runId": run_id, "games": games}, ensure_ascii=False) + "\n", encoding="utf-8")
    passthrough = ["--skip-build"] if args.skip_build else []
    if args.publish:
        passthrough.append("--publish")
    try:
        with ThreadPoolExecutor(max_workers=min(args.jobs, len(games))) as pool:
            futures = {}
            for game in games:
                env = dict(os.environ)
                env.update({
                    "GAMEWIKI_PERMIT_URL": f"http://127.0.0.1:{server.server_port}",
                    "GAMEWIKI_PERMIT_TOKEN": token,
                    "GAMEWIKI_VERIFY_PORT": str(_free_port()),
                    "PYTHONUNBUFFERED": "1",
                })
                future = pool.submit(_run_child, game, env, run_dir / "logs" / f"{slugify(game)}.log", passthrough)
                futures[future] = game
            for future in as_completed(futures):
                result = future.result()
                manifest["results"].append(result)
                with events_path.open("a", encoding="utf-8") as events:
                    events.write(json.dumps({"event": "game.finished", "at": _now(), **result}, ensure_ascii=False) + "\n")
                write_json(manifest_path, manifest)
    finally:
        server.shutdown()
        server.server_close()
    manifest["finishedAt"] = _now()
    manifest["status"] = "complete" if all(item["status"] == "complete" for item in manifest["results"]) else "failed"
    write_json(manifest_path, manifest)
    with events_path.open("a", encoding="utf-8") as events:
        events.write(json.dumps({"event": "run.finished", "at": manifest["finishedAt"], "status": manifest["status"]}, ensure_ascii=False) + "\n")
    print(f"\nRun: {run_id}\nManifest: {manifest_path}")
    return 0 if manifest["status"] == "complete" else 1


def _project_manifests():
    for path in sorted(PROJECTS_ROOT.glob("*/.gamewiki/manifest.json")):
        try:
            yield path, read_json(path)
        except Exception:
            continue


def status(argv: list[str]) -> int:
    slug = argv[0] if argv else None
    found = False
    for path, manifest in _project_manifests():
        if slug and manifest.get("slug") != slug:
            continue
        found = True
        print(f"{manifest.get('slug', path.parent.parent.name):32} {manifest.get('status', 'unknown'):10} {manifest.get('canonicalGameName') or manifest.get('game', '')}")
    return 0 if found or not slug else 1


def logs(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gamewiki.py logs")
    parser.add_argument("slug")
    parser.add_argument("--tail", type=int, default=100)
    args = parser.parse_args(argv)
    log_dir = PROJECTS_ROOT / args.slug / ".gamewiki" / "logs"
    candidates = sorted(log_dir.glob("orchestrator-*.log"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        print(f"No orchestrator log found for {args.slug}", file=sys.stderr)
        return 1
    lines = candidates[-1].read_text(encoding="utf-8", errors="replace").splitlines()
    print("\n".join(lines[-args.tail:]))
    return 0


def resume(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Usage: python gamewiki.py resume <slug>", file=sys.stderr)
        return 2
    manifest = read_json(PROJECTS_ROOT / argv[0] / ".gamewiki" / "manifest.json")
    game = str(manifest.get("canonicalGameName") or manifest.get("game") or "").strip()
    if not game:
        print("Manifest has no game name", file=sys.stderr)
        return 1
    return subprocess.call([sys.executable, str(ROOT / "gamewiki.py"), game], cwd=ROOT)


COMMANDS = {"run-many": run_many, "status": status, "logs": logs, "resume": resume}


def dispatch(command: str, argv: list[str]) -> int:
    return COMMANDS[command](argv)
