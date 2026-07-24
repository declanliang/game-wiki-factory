"""Production supervisor and observability commands for the Game Wiki Factory."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
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
PROJECTS_ROOT = Path(os.environ.get("GAMEWIKI_PROJECTS_ROOT", ROOT.parent)).expanduser().resolve()
RUNTIME_ROOT = ROOT / ".gamewiki" / "runs"


def normalize_manual_keywords(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("config.manualKeywords must be an array of strings")
    if len(value) > 200:
        raise ValueError("config.manualKeywords cannot contain more than 200 items")
    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"config.manualKeywords[{index}] must be a string")
        keyword = " ".join(item.split())
        if not keyword:
            raise ValueError(f"config.manualKeywords[{index}] cannot be empty")
        if len(keyword) > 200:
            raise ValueError(f"config.manualKeywords[{index}] cannot exceed 200 characters")
        marker = keyword.casefold()
        if marker not in seen:
            seen.add(marker)
            normalized.append(keyword)
    return normalized


def _config_command(config: dict[str, object]) -> tuple[str, list[str]]:
    allowed = {"schemaVersion", "taskType", "operation", "game", "platform", "officialUrl", "siteUrl", "publish", "refresh", "manualKeywords"}
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise ValueError(f"unknown config field(s): {', '.join(unknown)}")
    task_type = str(config.get("taskType") or "site").casefold()
    if task_type != "site":
        raise ValueError("foreground --config only accepts taskType=site; submit ads through jobs")
    operation = str(config.get("operation") or "new").casefold()
    if operation not in {"auto", "new"}:
        raise ValueError("config.operation must be new; legacy rebuild jobs are no longer accepted")
    game_value = config.get("game")
    if not isinstance(game_value, str) or not game_value.strip():
        raise ValueError("config.game must be a non-empty string")
    # JSON can legally contain escaped newlines. Collapse all whitespace so an
    # accidental line break never becomes part of identity or search queries.
    game = " ".join(game_value.split())
    platform = str(config.get("platform") or "auto").casefold()
    if platform not in {"auto", "roblox", "steam"}:
        raise ValueError("config.platform must be auto, roblox, or steam")
    args = ["--platform", platform]
    for field, flag in (("officialUrl", "--official-url"), ("siteUrl", "--site-url")):
        value = config.get(field)
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"config.{field} must be a non-empty string when supplied")
            args.extend([flag, value.strip()])
    publish = config.get("publish", False)
    if not isinstance(publish, bool):
        raise ValueError("config.publish must be true or false")
    if publish:
        args.append("--publish")
    for keyword in normalize_manual_keywords(config.get("manualKeywords")):
        args.extend(["--manual-keyword", keyword])
    refresh = config.get("refresh") or {}
    if not isinstance(refresh, dict):
        raise ValueError("config.refresh must be an object")
    refresh_flags = {
        "basicInfo": "--refresh-basic",
        "keywords": "--recluster-keywords",
        "articles": "--overwrite-articles",
    }
    unknown_refresh = sorted(set(refresh) - set(refresh_flags))
    if unknown_refresh:
        raise ValueError(f"unknown config.refresh field(s): {', '.join(unknown_refresh)}")
    for field, flag in refresh_flags.items():
        enabled = refresh.get(field, False)
        if not isinstance(enabled, bool):
            raise ValueError(f"config.refresh.{field} must be true or false")
        if enabled:
            args.append(flag)
    return game, args


def run_config(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gamewiki.py --config")
    parser.add_argument("config", type=Path)
    args = parser.parse_args(argv)
    config_path = args.config.expanduser().resolve()
    try:
        config = read_json(config_path)
        game, passthrough = _config_command(config)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    slug = slugify(game)
    attempt = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    temporary_log_dir = RUNTIME_ROOT / "config"
    temporary_log_dir.mkdir(parents=True, exist_ok=True)
    temporary_log = temporary_log_dir / f"{attempt}-{slug}.log"
    command = [sys.executable, str(ROOT / "gamewiki.py"), game, *passthrough]
    print(f"[config] {config_path}")
    print(f"[log] {temporary_log}")
    with temporary_log.open("w", encoding="utf-8") as log:
        log.write(f"config={config_path}\nstarted={_now()}\n")
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            log.flush()
            print(line, end="", flush=True)
        code = process.wait()
        log.write(f"\nfinished={_now()}\nexitCode={code}\n")
    project_state = PROJECTS_ROOT / slug / ".gamewiki"
    if project_state.is_dir():
        saved_config = project_state / "configs" / f"{attempt}.json"
        write_json(saved_config, config)
        final_log = project_state / "logs" / f"{attempt}-config.log"
        final_log.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(temporary_log, final_log)
        print(f"[saved-config] {saved_config}")
        print(f"[saved-log] {final_log}")
    return code


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


def _parse_game_spec(line: str) -> dict[str, object]:
    """Parse a backward-compatible name or name/platform/official-URL TSV row."""
    fields = [field.strip() for field in line.split("\t")]
    if len(fields) == 1 and fields[0]:
        return {"game": fields[0], "args": []}
    if len(fields) != 3 or not all(fields):
        raise ValueError(
            "games-file rows must be GAME NAME or GAME NAME<TAB>PLATFORM<TAB>OFFICIAL_URL"
        )
    game, platform, official_url = fields
    platform = platform.casefold()
    if platform not in {"roblox", "steam"}:
        raise ValueError(f"unsupported platform {platform!r} for {game!r}")
    return {
        "game": game,
        "platform": platform,
        "officialUrl": official_url,
        "args": ["--platform", platform, "--official-url", official_url],
    }


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
    tasks: list[dict[str, object]] = [{"game": game, "args": []} for game in args.games]
    if args.games_file:
        for line in args.games_file.read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                try:
                    tasks.append(_parse_game_spec(line))
                except ValueError as exc:
                    parser.error(str(exc))
    unique_tasks: dict[str, dict[str, object]] = {}
    for task in tasks:
        unique_tasks.setdefault(str(task["game"]), task)
    tasks = list(unique_tasks.values())
    games = [str(task["game"]) for task in tasks]
    if not tasks:
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
    manifest = {
        "schemaVersion": 1, "runId": run_id, "status": "running",
        "startedAt": _now(), "games": games,
        "taskSpecs": [
            {key: value for key, value in task.items() if key != "args"}
            for task in tasks
        ],
        "results": [],
    }
    write_json(manifest_path, manifest)
    events_path = run_dir / "events.jsonl"
    events_path.write_text(json.dumps({"event": "run.started", "at": manifest["startedAt"], "runId": run_id, "games": games}, ensure_ascii=False) + "\n", encoding="utf-8")
    passthrough = ["--skip-build"] if args.skip_build else []
    if args.publish:
        passthrough.append("--publish")
    try:
        with ThreadPoolExecutor(max_workers=min(args.jobs, len(games))) as pool:
            futures = {}
            for task in tasks:
                game = str(task["game"])
                env = dict(os.environ)
                env.update({
                    "GAMEWIKI_PERMIT_URL": f"http://127.0.0.1:{server.server_port}",
                    "GAMEWIKI_PERMIT_TOKEN": token,
                    "GAMEWIKI_VERIFY_PORT": str(_free_port()),
                    "PYTHONUNBUFFERED": "1",
                })
                future = pool.submit(
                    _run_child, game, env,
                    run_dir / "logs" / f"{slugify(game)}.log",
                    [*passthrough, *[str(item) for item in task.get("args", [])]],
                )
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


COMMANDS = {"run-config": run_config, "run-many": run_many, "status": status, "logs": logs, "resume": resume}


def dispatch(command: str, argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    return COMMANDS[command](argv)
