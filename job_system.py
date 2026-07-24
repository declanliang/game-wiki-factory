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

from factory_cli import PermitState, _config_command, _handler, normalize_manual_keywords
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
          result_json TEXT,
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
        CREATE TABLE IF NOT EXISTS notifications (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_id INTEGER NOT NULL UNIQUE,
          status TEXT NOT NULL DEFAULT 'pending',
          attempts INTEGER NOT NULL DEFAULT 0,
          available_at TEXT NOT NULL,
          delivered_at TEXT,
          last_error TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(event_id) REFERENCES events(id)
        );
        CREATE INDEX IF NOT EXISTS idx_notifications_pending
          ON notifications(status, available_at, id);
        """
    )
    columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)").fetchall()}
    if "result_json" not in columns:
        try:
            db.execute("ALTER TABLE jobs ADD COLUMN result_json TEXT")
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).casefold():
                raise
    return db


def _event(
    db: sqlite3.Connection,
    job_id: str,
    event: str,
    *,
    notify: bool = False,
    **detail: Any,
) -> int:
    cursor = db.execute(
        "INSERT INTO events(job_id,timestamp,event,detail_json) VALUES(?,?,?,?)",
        (job_id, _now(), event, json.dumps(detail, ensure_ascii=False)),
    )
    event_id = int(cursor.lastrowid)
    if notify:
        now = _now()
        db.execute(
            """INSERT OR IGNORE INTO notifications(event_id,status,available_at,created_at,updated_at)
               VALUES(?,'pending',?,?,?)""",
            (event_id, now, now, now),
        )
    return event_id


def pending_notifications(limit: int = 50) -> list[dict[str, Any]]:
    """Return durable, non-secret state changes awaiting operator delivery."""
    with connect() as db:
        rows = db.execute(
            """SELECT n.id AS notification_id,n.attempts,e.id AS event_id,e.job_id,
                      e.timestamp,e.event,e.detail_json,j.game,j.status AS current_status,j.current_stage,
                      j.attempts AS job_attempts,j.max_attempts,j.log_path,j.result_json
               FROM notifications n
               JOIN events e ON e.id=n.event_id
               JOIN jobs j ON j.id=e.job_id
               WHERE n.status='pending' AND n.available_at <= ?
               ORDER BY n.id LIMIT ?""",
            (_now(), max(1, min(limit, 200))),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["detail"] = json.loads(item.pop("detail_json") or "{}")
        item["event_status"] = item["detail"].get("status", item["current_status"])
        raw_result = item.pop("result_json", None)
        if raw_result:
            item["result"] = json.loads(raw_result)
        item["needsAttention"] = item["event_status"] in {"needs_attention", "failed"}
        result.append(item)
    return result


def acknowledge_notifications(notification_ids: list[int]) -> int:
    if not notification_ids:
        return 0
    placeholders = ",".join("?" for _ in notification_ids)
    now = _now()
    with connect() as db:
        return db.execute(
            f"""UPDATE notifications SET status='delivered',delivered_at=?,updated_at=?
                WHERE status='pending' AND id IN ({placeholders})""",
            (now, now, *notification_ids),
        ).rowcount


def defer_notification(notification_id: int, error: str) -> None:
    """Keep a failed delivery pending with bounded exponential backoff."""
    with connect() as db:
        row = db.execute(
            "SELECT attempts FROM notifications WHERE id=? AND status='pending'",
            (notification_id,),
        ).fetchone()
        if row is None:
            return
        attempts = int(row["attempts"]) + 1
        delay = min(1800, 30 * (2 ** min(attempts - 1, 6)))
        available = (
            datetime.now(timezone.utc) + timedelta(seconds=delay)
        ).replace(microsecond=0).isoformat()
        db.execute(
            """UPDATE notifications SET attempts=?,available_at=?,last_error=?,updated_at=?
               WHERE id=? AND status='pending'""",
            (attempts, available, error[-500:], _now(), notification_id),
        )


def normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    task_type = str(config.get("taskType") or "site").strip().casefold()
    if task_type == "ads":
        raise ValueError(
            "taskType ads is unavailable in the Cloudflare Pages workflow; "
            "configure AD_* environment variables manually in Cloudflare Pages"
        )
    if task_type != "site":
        raise ValueError("config.taskType must be site or ads")
    allowed = {
        "schemaVersion", "taskType", "operation", "game", "platform", "officialUrl",
        "siteUrl", "publish", "refresh", "manualKeywords",
    }
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise ValueError(f"unknown config field(s): {', '.join(unknown)}")
    normalized = dict(config)
    normalized["schemaVersion"] = 3
    normalized["taskType"] = "site"
    normalized["game"] = " ".join(str(config.get("game") or "").split())
    if not normalized["game"]:
        raise ValueError("config.game must be a non-empty string")
    normalized.setdefault("platform", "auto")
    normalized.setdefault("publish", False)
    operation = str(normalized.get("operation") or "new").strip().casefold()
    if operation not in {"auto", "new"}:
        raise ValueError("config.operation must be new; legacy rebuild jobs are no longer accepted")
    normalized["operation"] = "new"
    normalized["manualKeywords"] = normalize_manual_keywords(
        normalized.get("manualKeywords")
    )
    publication: dict[str, Any] = {}
    # Background jobs publish the private GitHub repository only. Cloudflare
    # Pages connection, domain selection, and runtime variables remain operator-owned.
    publication.setdefault("skipVercel", True)
    normalized["publication"] = publication
    # Validate the fields shared with the foreground CLI.
    foreground = {k: normalized[k] for k in ("schemaVersion", "game", "platform", "officialUrl", "siteUrl", "publish", "refresh", "manualKeywords") if k in normalized}
    foreground["schemaVersion"] = 1
    _config_command(foreground)
    return normalized


def _submit_normalized(config: dict[str, Any], source: str, *, max_attempts: int = 4) -> str:
    display_name = str(config.get("game") or config.get("domain_name") or "task")
    slug = slugify(display_name)
    job_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{slug}-{uuid.uuid4().hex[:6]}"
    now = _now()
    with connect() as db:
        db.execute(
            """INSERT INTO jobs(id,game,slug,config_json,status,max_attempts,available_at,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (job_id, display_name, slug, json.dumps(config, ensure_ascii=False), "queued", max_attempts, now, now, now),
        )
        _event(db, job_id, "job.submitted", configPath=source)
    return job_id


def submit(config_path: Path, *, max_attempts: int = 4) -> str:
    resolved = config_path.expanduser().resolve()
    config = normalize_config(read_json(resolved))
    return _submit_normalized(config, str(resolved), max_attempts=max_attempts)


def submit_batch(config_path: Path, *, max_attempts: int = 4) -> list[str]:
    resolved = config_path.expanduser().resolve()
    value = read_json(resolved)
    if not isinstance(value, dict):
        raise ValueError("batch config must be an object")
    allowed = {"schemaVersion", "taskType", "batchName", "defaults", "games"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"unknown batch field(s): {', '.join(unknown)}")
    if str(value.get("taskType") or "siteBatch") != "siteBatch":
        raise ValueError("batch taskType must be siteBatch")
    defaults = value.get("defaults") or {}
    games = value.get("games")
    if not isinstance(defaults, dict) or not isinstance(games, list) or not games:
        raise ValueError("batch defaults must be an object and games must be a non-empty array")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(games):
        if not isinstance(item, dict):
            raise ValueError(f"games[{index}] must be an object")
        merged = {**defaults, **item, "taskType": "site"}
        config = normalize_config(merged)
        identity = slugify(config["game"])
        if identity in seen:
            raise ValueError(f"duplicate game in batch: {config['game']}")
        seen.add(identity)
        normalized.append(config)
    return [
        _submit_normalized(config, f"{resolved}#games[{index}]", max_attempts=max_attempts)
        for index, config in enumerate(normalized)
    ]


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
               -- A previously-started job that only needs a transient retry must
               -- not be starved by a large batch submitted in the same second.
               ORDER BY CASE WHEN status='retry_wait' THEN 0 ELSE 1 END,
                        available_at, created_at, id
               LIMIT 1""",
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


def _heartbeat(job_id: str, slug: str, worker: str, stop: threading.Event, lease_seconds: int, task_type: str = "site") -> None:
    while not stop.wait(max(10, lease_seconds // 3)):
        expires = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).replace(microsecond=0).isoformat()
        projects_root = Path(os.environ.get("GAMEWIKI_PROJECTS_ROOT", ROOT.parent)).expanduser().resolve()
        manifest_path = projects_root / slug / ".gamewiki" / "manifest.json"
        stage = "ads" if task_type == "ads" else None
        if task_type == "site" and manifest_path.is_file():
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
    "api 500", "api 502", "api 503", "api 504", "api 520", "api 522", "api 524",
    "all_channels_circuit_broken",
    "bad gateway", "service unavailable", "rate limit", "dns",
)
ATTENTION_PATTERNS = (
    "too close to select safely", "api key", "unauthorized", "forbidden",
    "schema", "permission", "identity", "candidate",
)
QUOTA_PATTERNS = (
    "insufficient_user_quota", "insufficient quota", "quota exceeded",
    "quota exhausted", "insufficient balance", "balance insufficient",
    "balance exhausted", "insufficient credits", "credits exhausted",
    "credit balance", "余额不足", "额度不足",
)


def classify_failure(text: str) -> str:
    lowered = text.casefold()
    if any(pattern in lowered for pattern in QUOTA_PATTERNS):
        return "quota_exhausted"
    if any(pattern in lowered for pattern in ATTENTION_PATTERNS):
        return "needs_attention"
    if any(pattern in lowered for pattern in TRANSIENT_PATTERNS):
        return "retryable"
    return "needs_attention"


def _execution_config(config: dict[str, Any], attempt_number: int) -> dict[str, Any]:
    result = {k: config[k] for k in ("game", "platform", "officialUrl", "siteUrl", "manualKeywords") if k in config}
    result["schemaVersion"] = 1
    result["publish"] = False
    if attempt_number != 1:
        # A retry resumes the checkpoints written by the previous attempt.  It must
        # never repeat paid refresh work merely because a later stage failed.
        result["refresh"] = {"basicInfo": False, "keywords": False, "articles": False}
    else:
        requested = config.get("refresh") or {}
        result["refresh"] = {
            "basicInfo": bool(requested.get("basicInfo", False)),
            "keywords": bool(requested.get("keywords", False)),
            "articles": bool(requested.get("articles", False)),
        }
    return result


def _ad_execution_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return the private worker input; raw code never reaches console output."""
    return config


def _new_workspace_conflict(slug: str, attempt_number: int) -> Path | None:
    """Reject a newly submitted site job if its workspace is not empty."""
    if attempt_number != 1:
        return None
    projects_root = Path(os.environ.get("GAMEWIKI_PROJECTS_ROOT", ROOT.parent)).expanduser().resolve()
    project = (projects_root / slug).resolve()
    if project.parent != projects_root:
        raise RuntimeError("refusing to inspect a project outside GAMEWIKI_PROJECTS_ROOT")
    return project if project.exists() else None


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


def _completion_result(config: dict[str, Any], slug: str) -> dict[str, Any]:
    """Persist a non-secret acceptance summary before workspace cleanup."""
    projects_root = Path(os.environ.get("GAMEWIKI_PROJECTS_ROOT", ROOT.parent)).expanduser().resolve()
    project = (projects_root / slug).resolve()
    task_type = str(config.get("taskType") or "site")
    if task_type == "ads":
        receipt = read_json(project / ".gamewiki" / "ads.json")
        return {
            "taskType": "ads",
            "domainName": receipt.get("domainName"),
            "vercelProject": receipt.get("vercelProject"),
            "verification": receipt.get("verification"),
            "placementCount": len(receipt.get("placements") or []),
        }
    receipt = read_json(project / ".gamewiki" / "publish.json") if config.get("publish") else {}
    stages = receipt.get("stages") or {}
    plan_path = project / "intake" / "site-plan.json"
    plan = read_json(plan_path) if plan_path.is_file() else {}
    release_path = project / "intake" / "factory-release.json"
    release = read_json(release_path) if release_path.is_file() else {}
    return {
        "taskType": "site",
        "factoryRelease": release.get("release"),
        "articles": {
            "english": len(list((project / "content" / "en").rglob("*.mdx"))),
            "allLanguages": len(list((project / "content").rglob("*.mdx"))),
        },
        "categories": [
            item.get("id") for item in plan.get("categories") or []
            if item.get("status") == "published"
        ],
        "github": stages.get("github"),
        "hosting": stages.get("hosting"),
        "onlineVerification": stages.get("onlineVerification"),
    }


def _publish_command(config: dict[str, Any], slug: str) -> list[str]:
    publication = config.get("publication") or {}
    command = [sys.executable, str(ROOT / "gamewiki.py"), "publish", slug]
    if publication.get("githubOwner"):
        command.extend(["--owner", str(publication["githubOwner"])])
    if publication.get("githubRepo"):
        command.extend(["--repo", str(publication["githubRepo"])])
    if publication.get("vercelProject"):
        command.extend(["--vercel-project", str(publication["vercelProject"])])
    if publication.get("skipVercel", True):
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
    task_type = str(config.get("taskType") or "site")
    workspace_conflict = (
        _new_workspace_conflict(job["slug"], attempt) if task_type == "site" else None
    )
    write_json(
        config_path,
        _ad_execution_config(config) if task_type == "ads" else _execution_config(config, attempt),
    )
    env = build_subprocess_env(ROOT)
    stop = threading.Event()
    heartbeat = threading.Thread(target=_heartbeat, args=(job_id, job["slug"], worker, stop, lease_seconds, task_type), daemon=True)
    heartbeat.start()
    with connect() as db:
        initial_stage = "ads" if task_type == "ads" else "pipeline"
        db.execute("UPDATE jobs SET log_path=?,current_stage=?,updated_at=? WHERE id=?", (str(log_path), initial_stage, _now(), job_id))
        db.execute(
            "INSERT INTO attempts(job_id,number,worker,status,started_at,log_path) VALUES(?,?,?,?,?,?)",
            (job_id, attempt, worker, "running", _now(), str(log_path)),
        )
        _event(db, job_id, "attempt.started", attempt=attempt, worker=worker)
    code = 1
    completion_result: dict[str, Any] | None = None
    try:
        with log_path.open("w", encoding="utf-8") as log:
            log.write(f"job={job_id}\nattempt={attempt}\nstarted={_now()}\n")
            if workspace_conflict is not None:
                log.write(
                    "[failed] new site job requires an empty workspace; "
                    f"existing workspace: {workspace_conflict}\n"
                )
            else:
                command = (
                    [sys.executable, str(ROOT / "gamewiki.py"), "ads", "import", "--config", str(config_path)]
                    if task_type == "ads"
                    else [sys.executable, str(ROOT / "gamewiki.py"), "--config", str(config_path)]
                )
                code = _run_process(command, log, env, job_id)
            if code == 0 and task_type == "site" and config.get("publish"):
                with connect() as db:
                    db.execute("UPDATE jobs SET current_stage='publish',updated_at=? WHERE id=?", (_now(), job_id))
                code = _run_process(_publish_command(config, job["slug"]), log, env, job_id)
            if code == 0:
                try:
                    completion_result = _completion_result(config, job["slug"])
                except (OSError, ValueError, KeyError) as exc:
                    log.write(f"\n[failed] could not persist acceptance result: {exc}\n")
                    code = 1
            if code == 0 and task_type == "site":
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
               last_error=?,finished_at=?,updated_at=?,result_json=?,
               current_stage=CASE WHEN ?='succeeded' THEN 'complete' ELSE current_stage END
               WHERE id=?""",
            (
                status,
                available,
                None if code == 0 else tail[-2000:],
                _now() if status in TERMINAL | {"needs_attention"} else None,
                _now(),
                json.dumps(completion_result, ensure_ascii=False) if completion_result is not None else None,
                status,
                job_id,
            ),
        )
        db.execute(
            """UPDATE attempts SET status=?,finished_at=?,exit_code=?,error_class=?
               WHERE job_id=? AND number=?""",
            (status, _now(), code, error_class, job_id, attempt),
        )
        _event(
            db,
            job_id,
            "attempt.finished",
            notify=status in {"succeeded", "failed", "needs_attention", "cancelled"},
            attempt=attempt,
            status=status,
            exitCode=code,
            errorClass=error_class,
        )


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
    raw_result = result.pop("result_json", None)
    if raw_result:
        result["result"] = json.loads(raw_result)
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
    batch_source = batch.add_mutually_exclusive_group(required=True)
    batch_source.add_argument("--config", type=Path)
    batch_source.add_argument("--config-dir", type=Path)
    batch.add_argument("--max-attempts", type=int, default=4)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--json", action="store_true")
    notifications = sub.add_parser("notifications")
    notifications.add_argument("--json", action="store_true")
    notifications.add_argument("--limit", type=int, default=50)
    notifications.add_argument("--ack", type=int, nargs="+")
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
        if args.config:
            for job_id in submit_batch(args.config, max_attempts=args.max_attempts):
                print(job_id)
        else:
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
    if args.command == "notifications":
        if args.ack:
            count = acknowledge_notifications(args.ack)
            print(json.dumps({"acknowledged": count}, ensure_ascii=False) if args.json else count)
            return 0
        items = pending_notifications(args.limit)
        if args.json:
            print(json.dumps(items, ensure_ascii=False, indent=2))
        else:
            for item in items:
                print(
                    f"{item['notification_id']:6} {item['event_status']:16} "
                    f"{item['job_id']} {item['game']}"
                )
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
            db.execute("UPDATE jobs SET status='queued',available_at=?,cancel_requested=0,last_error=NULL,finished_at=NULL,result_json=NULL,updated_at=? WHERE id=?", (_now(), _now(), args.job_id))
            _event(db, args.job_id, "job.retried")
        elif args.command == "cancel":
            db.execute("UPDATE jobs SET cancel_requested=1,status=CASE WHEN status IN ('queued','retry_wait','needs_attention') THEN 'cancelled' ELSE status END,updated_at=? WHERE id=?", (_now(), args.job_id))
            cancelled = db.execute("SELECT status FROM jobs WHERE id=?", (args.job_id,)).fetchone()
            _event(
                db,
                args.job_id,
                "job.cancel_requested",
                notify=bool(cancelled and cancelled["status"] == "cancelled"),
                status=cancelled["status"] if cancelled else None,
            )
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
