"""Persistent SQLite job queue and worker for Game Wiki Factory."""

from __future__ import annotations

import argparse
import json
import os
import signal
import shutil
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from factory_cli import PermitState, _config_command, _handler
from http.server import ThreadingHTTPServer
from orchestrate_wiki import build_subprocess_env, read_json, slugify, write_json


ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = ROOT / ".gamewiki" / "jobs"
TERMINAL = {"succeeded", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def data_dir() -> Path:
    path = Path(os.environ.get("GAMEWIKI_DATA_DIR", DEFAULT_DATA_DIR)).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "jobs.sqlite3"


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(db_path(), timeout=30, isolation_level=None, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=30000")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY,
          game TEXT NOT NULL,
          slug TEXT NOT NULL,
          config_json TEXT NOT NULL,
          status TEXT NOT NULL,
          current_stage TEXT,
          attempts INTEGER NOT NULL DEFAULT 0,
          max_attempts INTEGER NOT NULL DEFAULT 4,
          available_at TEXT NOT NULL,
          lease_owner TEXT,
          lease_expires_at TEXT,
          cancel_requested INTEGER NOT NULL DEFAULT 0,
          last_error TEXT,
          log_path TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_claim
          ON jobs(status, available_at, created_at);
        CREATE TABLE IF NOT EXISTS attempts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          job_id TEXT NOT NULL,
          number INTEGER NOT NULL,
          worker TEXT NOT NULL,
          status TEXT NOT NULL,
          started_at TEXT NOT NULL,
          finished_at TEXT,
          exit_code INTEGER,
          error_class TEXT,
          log_path TEXT NOT NULL,
          FOREIGN KEY(job_id) REFERENCES jobs(id)
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          job_id TEXT NOT NULL,
          timestamp TEXT NOT NULL,
          event TEXT NOT NULL,
          detail_json TEXT NOT NULL DEFAULT '{}'
        );
        """
    )
    return db


def _event(db: sqlite3.Connection, job_id: str, event: str, **detail: Any) -> None:
    db.execute(
        "INSERT INTO events(job_id,timestamp,event,detail_json) VALUES(?,?,?,?)",
        (job_id, _now(), event, json.dumps(detail, ensure_ascii=False)),
    )


def normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "schemaVersion", "game", "platform", "officialUrl", "siteUrl", "publish",
        "refresh", "fullBuild", "publication",
    }
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise ValueError(f"unknown config field(s): {', '.join(unknown)}")
    normalized = dict(config)
    normalized["schemaVersion"] = 2
    normalized["game"] = " ".join(str(config.get("game") or "").split())
    if not normalized["game"]:
        raise ValueError("config.game must be a non-empty string")
    normalized.setdefault("platform", "auto")
    normalized.setdefault("publish", False)
    normalized.setdefault("fullBuild", False)
    publication = normalized.get("publication") or {}
    if not isinstance(publication, dict):
        raise ValueError("config.publication must be an object")
    publication_allowed = {
        "githubOwner", "githubRepo", "reuseExisting", "replaceRepositoryContents",
        "vercelProject", "skipVercel",
    }
    unknown_publication = sorted(set(publication) - publication_allowed)
    if unknown_publication:
        raise ValueError(f"unknown publication field(s): {', '.join(unknown_publication)}")
    normalized["publication"] = publication
    # Validate the fields shared with the foreground CLI.
    foreground = {k: normalized[k] for k in ("schemaVersion", "game", "platform", "officialUrl", "siteUrl", "publish", "refresh") if k in normalized}
    foreground["schemaVersion"] = 1
    _config_command(foreground)
    return normalized


def submit(config_path: Path, *, max_attempts: int = 4) -> str:
    config = normalize_config(read_json(config_path.expanduser().resolve()))
    job_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{slugify(config['game'])}-{uuid.uuid4().hex[:6]}"
    now = _now()
    with connect() as db:
        db.execute(
            """INSERT INTO jobs(id,game,slug,config_json,status,max_attempts,available_at,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (job_id, config["game"], slugify(config["game"]), json.dumps(config, ensure_ascii=False), "queued", max_attempts, now, now, now),
        )
        _event(db, job_id, "job.submitted", configPath=str(config_path))
    return job_id


def _requeue_stale(db: sqlite3.Connection) -> int:
    now = _now()
    rows = db.execute(
        "SELECT id FROM jobs WHERE status='running' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?",
        (now,),
    ).fetchall()
    for row in rows:
        db.execute(
            "UPDATE jobs SET status='queued',lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?",
            (now, row["id"]),
        )
        _event(db, row["id"], "job.lease_recovered")
    return len(rows)


def claim(worker: str, lease_seconds: int = 90) -> sqlite3.Row | None:
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        _requeue_stale(db)
        row = db.execute(
            """SELECT * FROM jobs
               WHERE status IN ('queued','retry_wait') AND available_at <= ? AND cancel_requested=0
               ORDER BY created_at LIMIT 1""",
            (_now(),),
        ).fetchone()
        if row is None:
            db.execute("COMMIT")
            return None
        expires = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).replace(microsecond=0).isoformat()
        updated = db.execute(
            """UPDATE jobs SET status='running',lease_owner=?,lease_expires_at=?,attempts=attempts+1,
               started_at=COALESCE(started_at,?),updated_at=? WHERE id=? AND status IN ('queued','retry_wait')""",
            (worker, expires, _now(), _now(), row["id"]),
        ).rowcount
        db.execute("COMMIT")
        return db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone() if updated else None
    finally:
        db.close()


def _heartbeat(job_id: str, slug: str, worker: str, stop: threading.Event, lease_seconds: int) -> None:
    while not stop.wait(max(10, lease_seconds // 3)):
        expires = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).replace(microsecond=0).isoformat()
        projects_root = Path(os.environ.get("GAMEWIKI_PROJECTS_ROOT", ROOT.parent)).expanduser().resolve()
        manifest_path = projects_root / slug / ".gamewiki" / "manifest.json"
        stage = None
        if manifest_path.is_file():
            try:
                manifest = read_json(manifest_path)
                stages = manifest.get("stages") or {}
                stage = next(reversed(stages), None) if isinstance(stages, dict) else None
            except (OSError, ValueError, RuntimeError):
                pass
        with connect() as db:
            db.execute(
                "UPDATE jobs SET lease_expires_at=?,current_stage=COALESCE(?,current_stage),updated_at=? WHERE id=? AND lease_owner=? AND status='running'",
                (expires, stage, _now(), job_id, worker),
            )


TRANSIENT_PATTERNS = (
    "timed out", "timeout", "connection reset", "connection aborted", "temporary failure",
    "http 429", "status 429", "http 500", "http 502", "http 503", "http 504",
    "bad gateway", "service unavailable", "rate limit", "dns",
)
ATTENTION_PATTERNS = (
    "too close to select safely", "api key", "unauthorized", "forbidden", "insufficient",
    "quota", "balance", "schema", "permission", "identity", "candidate",
)


def classify_failure(text: str) -> str:
    lowered = text.casefold()
    if any(pattern in lowered for pattern in ATTENTION_PATTERNS):
        return "needs_attention"
    if any(pattern in lowered for pattern in TRANSIENT_PATTERNS):
        return "retryable"
    return "needs_attention"


def _execution_config(config: dict[str, Any], attempt_number: int) -> dict[str, Any]:
    result = {k: config[k] for k in ("game", "platform", "officialUrl", "siteUrl") if k in config}
    result["schemaVersion"] = 1
    result["publish"] = False
    if config.get("fullBuild") and attempt_number == 1:
        result["refresh"] = {"basicInfo": True, "keywords": True, "articles": True}
    else:
        result["refresh"] = {"basicInfo": False, "keywords": False, "articles": False}
    return result


def _prepare_full_build(config: dict[str, Any], slug: str, attempt_number: int) -> Path | None:
    """Move an old local project aside once so full_build starts from an empty workspace."""
    if not config.get("fullBuild") or attempt_number != 1:
        return None
    projects_root = Path(os.environ.get("GAMEWIKI_PROJECTS_ROOT", ROOT.parent)).expanduser().resolve()
    project = (projects_root / slug).resolve()
    if project.parent != projects_root:
        raise RuntimeError("refusing to rebuild a project outside GAMEWIKI_PROJECTS_ROOT")
    if not project.exists():
        return None
    backup = projects_root / f"{slug}.pre-full-build-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    if backup.exists():
        raise RuntimeError(f"full-build backup already exists: {backup}")
    project.rename(backup)
    return backup


def _prune_success_build_artifacts(config: dict[str, Any], slug: str) -> list[str]:
    """Release reproducible build caches after a successful published job."""
    enabled = os.environ.get("GAMEWIKI_PRUNE_SUCCESS_BUILD_ARTIFACTS", "1").strip().casefold()
    if not config.get("publish") or enabled in {"0", "false", "no", "off"}:
        return []
    projects_root = Path(os.environ.get("GAMEWIKI_PROJECTS_ROOT", ROOT.parent)).expanduser().resolve()
    project = (projects_root / slug).resolve()
    if project.parent != projects_root or not project.is_dir():
        return []
    removed: list[str] = []
    for name in ("node_modules", ".next"):
        target = (project / name).resolve()
        if target.parent != project or not target.is_dir():
            continue
        shutil.rmtree(target)
        removed.append(name)
    return removed


def _publish_command(config: dict[str, Any], slug: str) -> list[str]:
    publication = config.get("publication") or {}
    command = [sys.executable, str(ROOT / "gamewiki.py"), "publish", slug]
    if publication.get("githubOwner"):
        command.extend(["--owner", str(publication["githubOwner"])])
    if publication.get("githubRepo"):
        command.extend(["--repo", str(publication["githubRepo"])])
    if publication.get("replaceRepositoryContents"):
        command.append("--replace-existing")
    if publication.get("vercelProject"):
        command.extend(["--vercel-project", str(publication["vercelProject"])])
    if publication.get("skipVercel"):
        command.append("--skip-vercel")
    if config.get("siteUrl"):
        command.extend(["--site-url", str(config["siteUrl"])])
    return command


def _run_process(command: list[str], log, env: dict[str, str], job_id: str) -> int:
    process = subprocess.Popen(
        command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    assert process.stdout is not None
    while True:
        line = process.stdout.readline()
        if line:
            log.write(line)
            log.flush()
        elif process.poll() is not None:
            break
        with connect() as db:
            cancelled = db.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
        if cancelled and cancelled[0]:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
            return 130
    return process.wait()


def execute(job: sqlite3.Row, worker: str, lease_seconds: int = 90) -> None:
    config = json.loads(job["config_json"])
    job_id = job["id"]
    attempt = int(job["attempts"])
    runtime = data_dir()
    logs = runtime / "logs" / job_id
    configs = runtime / "configs" / job_id
    logs.mkdir(parents=True, exist_ok=True)
    configs.mkdir(parents=True, exist_ok=True)
    log_path = logs / f"attempt-{attempt}.log"
    config_path = configs / f"attempt-{attempt}.json"
    backup = _prepare_full_build(config, job["slug"], attempt)
    write_json(config_path, _execution_config(config, attempt))
    env = build_subprocess_env(ROOT)
    stop = threading.Event()
    heartbeat = threading.Thread(target=_heartbeat, args=(job_id, job["slug"], worker, stop, lease_seconds), daemon=True)
    heartbeat.start()
    with connect() as db:
        db.execute("UPDATE jobs SET log_path=?,current_stage='pipeline',updated_at=? WHERE id=?", (str(log_path), _now(), job_id))
        db.execute(
            "INSERT INTO attempts(job_id,number,worker,status,started_at,log_path) VALUES(?,?,?,?,?,?)",
            (job_id, attempt, worker, "running", _now(), str(log_path)),
        )
        _event(db, job_id, "attempt.started", attempt=attempt, worker=worker)
        if backup:
            _event(db, job_id, "workspace.archived", path=str(backup))
    code = 1
    try:
        with log_path.open("w", encoding="utf-8") as log:
            log.write(f"job={job_id}\nattempt={attempt}\nstarted={_now()}\n")
            code = _run_process([sys.executable, str(ROOT / "gamewiki.py"), "--config", str(config_path)], log, env, job_id)
            if code == 0 and config.get("publish"):
                with connect() as db:
                    db.execute("UPDATE jobs SET current_stage='publish',updated_at=? WHERE id=?", (_now(), job_id))
                code = _run_process(_publish_command(config, job["slug"]), log, env, job_id)
            if code == 0:
                try:
                    pruned = _prune_success_build_artifacts(config, job["slug"])
                    if pruned:
                        log.write(f"\nprunedBuildArtifacts={','.join(pruned)}\n")
                except OSError as exc:
                    # Publishing already succeeded; failure to delete a
                    # disposable cache must not fail the completed website.
                    log.write(f"\n[warning] could not prune build artifacts: {exc}\n")
            log.write(f"\nfinished={_now()}\nexitCode={code}\n")
    finally:
        stop.set()
        heartbeat.join(timeout=5)
    tail = log_path.read_text(encoding="utf-8", errors="replace")[-12000:]
    with connect() as db:
        cancelled = db.execute("SELECT cancel_requested,max_attempts FROM jobs WHERE id=?", (job_id,)).fetchone()
        if cancelled and cancelled["cancel_requested"]:
            status, error_class, available = "cancelled", "cancelled", _now()
        elif code == 0:
            status, error_class, available = "succeeded", None, _now()
        else:
            error_class = classify_failure(tail)
            if error_class == "retryable" and attempt < int(cancelled["max_attempts"]):
                delays = (30, 120, 600)
                delay = delays[min(attempt - 1, len(delays) - 1)]
                status = "retry_wait"
                available = (datetime.now(timezone.utc) + timedelta(seconds=delay)).replace(microsecond=0).isoformat()
            elif error_class == "retryable":
                status, available = "failed", _now()
            else:
                status, available = "needs_attention", _now()
        db.execute(
            """UPDATE jobs SET status=?,available_at=?,lease_owner=NULL,lease_expires_at=NULL,
               last_error=?,finished_at=?,updated_at=? WHERE id=?""",
            (status, available, None if code == 0 else tail[-2000:], _now() if status in TERMINAL | {"needs_attention"} else None, _now(), job_id),
        )
        db.execute(
            """UPDATE attempts SET status=?,finished_at=?,exit_code=?,error_class=?
               WHERE job_id=? AND number=?""",
            (status, _now(), code, error_class, job_id, attempt),
        )
        _event(db, job_id, "attempt.finished", attempt=attempt, status=status, exitCode=code, errorClass=error_class)


def worker_loop(concurrency: int, once: bool, poll_seconds: float = 3.0) -> int:
    stop = threading.Event()

    def handle_signal(*_args):
        stop.set()

    for name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), handle_signal)

    def runner(slot: int):
        identity = f"{os.uname().nodename if hasattr(os, 'uname') else os.environ.get('COMPUTERNAME','worker')}:{os.getpid()}:{slot}"
        idle_once = False
        while not stop.is_set():
            usage = shutil.disk_usage(data_dir())
            used_percent = (usage.used / usage.total) * 100 if usage.total else 0
            pause_percent = float(os.environ.get("GAMEWIKI_DISK_PAUSE_PERCENT", "80"))
            if used_percent >= pause_percent:
                if once:
                    break
                stop.wait(60)
                continue
            job = claim(identity)
            if job:
                idle_once = False
                execute(job, identity)
            elif once:
                idle_once = True
                break
            else:
                stop.wait(poll_seconds)
        return idle_once

    threads = [threading.Thread(target=runner, args=(slot,), daemon=False) for slot in range(concurrency)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return 0


def _job_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result.pop("config_json", None)
    return result


def jobs_cli(argv: list[str]) -> int:
    # Job logs intentionally preserve Unicode status markers.  Windows can
    # otherwise inherit a legacy GBK console encoding and fail while merely
    # displaying an otherwise healthy UTF-8 log.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="gamewiki.py jobs")
    sub = parser.add_subparsers(dest="command", required=True)
    submit_parser = sub.add_parser("submit")
    submit_parser.add_argument("--config", type=Path, required=True)
    submit_parser.add_argument("--max-attempts", type=int, default=4)
    batch = sub.add_parser("submit-batch")
    batch.add_argument("--config-dir", type=Path, required=True)
    batch.add_argument("--max-attempts", type=int, default=4)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--json", action="store_true")
    for name in ("status", "retry", "cancel"):
        command = sub.add_parser(name)
        command.add_argument("job_id")
        if name == "status":
            command.add_argument("--json", action="store_true")
    logs = sub.add_parser("logs")
    logs.add_argument("job_id")
    logs.add_argument("--tail", type=int, default=200)
    cleanup_parser = sub.add_parser("cleanup")
    cleanup_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "submit":
        print(submit(args.config, max_attempts=args.max_attempts))
        return 0
    if args.command == "submit-batch":
        paths = sorted(args.config_dir.expanduser().resolve().glob("*.json"))
        for path in paths:
            print(submit(path, max_attempts=args.max_attempts))
        return 0
    if args.command == "cleanup":
        projects_root = Path(os.environ.get("GAMEWIKI_PROJECTS_ROOT", ROOT.parent)).expanduser().resolve()
        success_hours = int(os.environ.get("GAMEWIKI_SUCCESS_RETENTION_HOURS", "72"))
        failed_days = int(os.environ.get("GAMEWIKI_FAILED_RETENTION_DAYS", "14"))
        now = datetime.now(timezone.utc)
        removed = []
        with connect() as db:
            rows = db.execute("SELECT id,slug,status,finished_at FROM jobs WHERE finished_at IS NOT NULL").fetchall()
        for row in rows:
            age = now - _parse_time(row["finished_at"])
            threshold = timedelta(hours=success_hours) if row["status"] == "succeeded" else timedelta(days=failed_days)
            project = (projects_root / row["slug"]).resolve()
            if age < threshold or project.parent != projects_root:
                continue
            candidates = [project, *projects_root.glob(f"{row['slug']}.pre-full-build-*")]
            for candidate in candidates:
                candidate = candidate.resolve()
                if candidate.parent != projects_root or not candidate.is_dir():
                    continue
                removed.append(str(candidate))
                if not args.dry_run:
                    shutil.rmtree(candidate)
        print(json.dumps({"dryRun": args.dry_run, "projects": removed}, ensure_ascii=False, indent=2))
        return 0
    with connect() as db:
        if args.command == "list":
            rows = db.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
            if args.json:
                print(json.dumps([_job_dict(row) for row in rows], ensure_ascii=False, indent=2))
            else:
                for row in rows:
                    print(f"{row['id']:60} {row['status']:16} {row['game']}")
            return 0
        row = db.execute("SELECT * FROM jobs WHERE id=?", (args.job_id,)).fetchone()
        if row is None:
            print("Job not found", file=sys.stderr)
            return 1
        if args.command == "status":
            print(json.dumps(_job_dict(row), ensure_ascii=False, indent=2) if args.json else f"{row['id']} {row['status']} stage={row['current_stage']} attempts={row['attempts']} log={row['log_path']}")
        elif args.command == "logs":
            path = Path(row["log_path"]) if row["log_path"] else None
            if not path or not path.is_file():
                print("No log available", file=sys.stderr)
                return 1
            print("\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-args.tail:]))
        elif args.command == "retry":
            db.execute("UPDATE jobs SET status='queued',available_at=?,cancel_requested=0,last_error=NULL,finished_at=NULL,updated_at=? WHERE id=?", (_now(), _now(), args.job_id))
            _event(db, args.job_id, "job.retried")
        elif args.command == "cancel":
            db.execute("UPDATE jobs SET cancel_requested=1,status=CASE WHEN status IN ('queued','retry_wait','needs_attention') THEN 'cancelled' ELSE status END,updated_at=? WHERE id=?", (_now(), args.job_id))
            _event(db, args.job_id, "job.cancel_requested")
    return 0


def worker_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gamewiki.py worker")
    parser.add_argument("--concurrency", type=int, default=int(os.environ.get("GAMEWIKI_JOB_CONCURRENCY", "2")))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--llm-concurrency", type=int, default=int(os.environ.get("GAMEWIKI_LLM_CONCURRENCY", "6")))
    parser.add_argument("--llm-per-key", type=int, default=int(os.environ.get("GAMEWIKI_LLM_PER_KEY", "2")))
    parser.add_argument("--build-concurrency", type=int, default=int(os.environ.get("GAMEWIKI_BUILD_CONCURRENCY", "1")))
    args = parser.parse_args(argv)
    if args.concurrency < 1:
        parser.error("--concurrency must be positive")
    state = PermitState(args.llm_concurrency, args.llm_per_key, args.build_concurrency)
    token = secrets.token_urlsafe(24)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state, token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    old_url = os.environ.get("GAMEWIKI_PERMIT_URL")
    old_token = os.environ.get("GAMEWIKI_PERMIT_TOKEN")
    os.environ["GAMEWIKI_PERMIT_URL"] = f"http://127.0.0.1:{server.server_port}"
    os.environ["GAMEWIKI_PERMIT_TOKEN"] = token
    os.environ["GAMEWIKI_VERIFY_PORT"] = "0"
    try:
        return worker_loop(args.concurrency, args.once)
    finally:
        server.shutdown()
        server.server_close()
        if old_url is None:
            os.environ.pop("GAMEWIKI_PERMIT_URL", None)
        else:
            os.environ["GAMEWIKI_PERMIT_URL"] = old_url
        if old_token is None:
            os.environ.pop("GAMEWIKI_PERMIT_TOKEN", None)
        else:
            os.environ["GAMEWIKI_PERMIT_TOKEN"] = old_token
