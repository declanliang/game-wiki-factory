"""Codex-backed recovery controller for bounded Game Wiki job repairs."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from job_system import _event, _now, connect, data_dir
from orchestrate_wiki import parse_dotenv, read_json, write_json


ROOT = Path(__file__).resolve().parent
DEFAULT_CODEX_TIMEOUT_SECONDS = 45 * 60

BLOCKED_PATTERNS = (
    "api key",
    "unauthorized",
    "forbidden",
    "insufficient",
    "quota",
    "balance",
    "permission",
    "secret-like",
    "github app authorization",
    "github repository visibility",
    "public repo",
    "public repository",
    "schema",
    "dns",
    "custom domain",
)

AI_RECOVERABLE_PATTERNS = (
    "article preflight",
    "translationerror",
    "translation failed",
    "formatting",
    "formatting issue",
    "duplicate title",
    "duplicate description",
    "title 未完成",
    "description 未完成",
    "未完成连接词",
    "格式化不完整",
    "mdx",
    "factory-release.json missing",
    "factory-release.json 缺失",
    "site-identity.json missing",
    "slug mismatch",
    "slug 不匹配",
    "output directory name mismatch",
    "next.js build",
    "page export",
    "export encountered errors",
    "cloudflare api returned http 500",
    "cloudflare api 返回 http 500",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
    "http 524",
    "origin_response_timeout",
)

ALLOWED_STAGES = {
    "articles",
    "siteCopy",
    "site",
    "dependencies",
    "pipeline",
    "publish",
    "gameProfile",
}


def _ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS agent2_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          job_id TEXT NOT NULL,
          number INTEGER NOT NULL,
          original_status TEXT NOT NULL,
          status TEXT NOT NULL,
          started_at TEXT NOT NULL,
          finished_at TEXT,
          log_path TEXT,
          report_path TEXT,
          action TEXT,
          last_error TEXT,
          UNIQUE(job_id, number)
        );
        CREATE INDEX IF NOT EXISTS idx_agent2_runs_job
          ON agent2_runs(job_id, id);
        """
    )


def _safe_project_dir(slug: str) -> Path | None:
    projects_root = Path(os.environ.get("GAMEWIKI_PROJECTS_ROOT", ROOT.parent)).expanduser().resolve()
    project = (projects_root / slug).resolve()
    if project.parent != projects_root or not project.is_dir():
        return None
    return project


def _redact(text: str, limit: int = 20000) -> str:
    value = text[-limit:]
    value = re.sub(
        r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*[^\s,'\"]+",
        r"\1=<redacted>",
        value,
    )
    value = re.sub(r"(?i)(bearer\s+)[a-z0-9._~+/=-]{16,}", r"\1<redacted>", value)
    value = re.sub(r"\b(sk-[A-Za-z0-9_-]{12,})\b", "<redacted-openai-key>", value)
    return value


def _read_tail(path: str | None, limit: int = 20000) -> str:
    if not path:
        return ""
    log_path = Path(path)
    if not log_path.is_file():
        return ""
    return _redact(log_path.read_text(encoding="utf-8", errors="replace"), limit=limit)


def _run_count(db: sqlite3.Connection, job_id: str) -> int:
    return int(
        db.execute(
            "SELECT COUNT(*) FROM agent2_runs WHERE job_id=? AND status<>'stale'",
            (job_id,),
        ).fetchone()[0]
    )


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _recover_stale_agent_repairs(db: sqlite3.Connection) -> int:
    stale_seconds = max(300, int(os.environ.get("GAMEWIKI_AGENT2_STALE_SECONDS", "5400")))
    now = datetime.now(timezone.utc)
    rows = db.execute(
        """SELECT r.job_id,r.number,r.original_status,r.started_at,j.game
           FROM agent2_runs r
           JOIN jobs j ON j.id=r.job_id
           WHERE r.status='running' AND j.status='agent_repair'"""
    ).fetchall()
    recovered = 0
    for row in rows:
        try:
            age = (now - _parse_time(row["started_at"])).total_seconds()
        except ValueError:
            age = stale_seconds + 1
        if age < stale_seconds:
            continue
        status = row["original_status"] if row["original_status"] in {"needs_attention", "failed"} else "needs_attention"
        error = f"Agent2 run {row['number']} exceeded stale timeout"
        db.execute(
            """UPDATE agent2_runs SET status='stale',finished_at=?,last_error=?
               WHERE job_id=? AND number=? AND status='running'""",
            (_now(), error, row["job_id"], row["number"]),
        )
        db.execute(
            """UPDATE jobs SET status=?,last_error=COALESCE(last_error,?),updated_at=?
               WHERE id=? AND status='agent_repair'""",
            (status, error, _now(), row["job_id"]),
        )
        _event(
            db,
            row["job_id"],
            "job.agent2_escalated",
            notify=True,
            run=row["number"],
            action="stale",
            escalationReason=error,
        )
        recovered += 1
    return recovered


def _is_eligible(row: sqlite3.Row) -> tuple[bool, str]:
    config = json.loads(row["config_json"] or "{}")
    if str(config.get("taskType") or "site") != "site":
        return False, "only site jobs are eligible"
    stage = str(row["current_stage"] or "")
    if stage not in ALLOWED_STAGES:
        return False, f"stage {stage or '<unknown>'} is outside agent2 scope"
    if row["quota_provider"]:
        return False, "quota circuit requires human credential action"
    error = str(row["last_error"] or "").casefold()
    if any(pattern in error for pattern in BLOCKED_PATTERNS):
        return False, "credentials, quota, schema, DNS, or security issue"
    if any(pattern in error for pattern in AI_RECOVERABLE_PATTERNS):
        return True, "matched bounded AI recovery pattern"
    if int(row["attempts"] or 0) > int(row["max_attempts"] or 4):
        return True, "retry budget exhausted with preserved workspace"
    return False, "no known agent2 recovery signal"


def _claim(limit: int) -> list[dict[str, Any]]:
    claimed: list[dict[str, Any]] = []
    max_runs = max(0, int(os.environ.get("GAMEWIKI_AGENT2_MAX_RUNS", "2")))
    with connect() as db:
        _ensure_schema(db)
        db.execute("BEGIN IMMEDIATE")
        _recover_stale_agent_repairs(db)
        rows = db.execute(
            """SELECT * FROM jobs
               WHERE status IN ('needs_attention','failed') AND cancel_requested=0
               ORDER BY updated_at LIMIT ?""",
            (max(1, min(limit, 50)),),
        ).fetchall()
        for row in rows:
            if len(claimed) >= limit:
                break
            eligible, reason = _is_eligible(row)
            if not eligible:
                continue
            prior_runs = _run_count(db, row["id"])
            if prior_runs >= max_runs:
                continue
            project = _safe_project_dir(row["slug"])
            if project is None:
                continue
            changed = db.execute(
                """UPDATE jobs SET status='agent_repair',lease_owner=NULL,lease_expires_at=NULL,
                          updated_at=?
                   WHERE id=? AND status IN ('needs_attention','failed') AND cancel_requested=0""",
                (_now(), row["id"]),
            ).rowcount
            if not changed:
                continue
            number = prior_runs + 1
            started = _now()
            runtime = data_dir() / "agent2" / row["id"]
            runtime.mkdir(parents=True, exist_ok=True)
            log_path = runtime / f"run-{number}.log"
            report_path = runtime / f"run-{number}-report.json"
            input_path = runtime / f"run-{number}-input.json"
            db.execute(
                """INSERT INTO agent2_runs(job_id,number,original_status,status,started_at,log_path,report_path)
                   VALUES(?,?,?,?,?,?,?)""",
                (row["id"], number, row["status"], "running", started, str(log_path), str(report_path)),
            )
            _event(db, row["id"], "job.agent2_claimed", run=number, reason=reason)
            db.execute(
                """UPDATE notifications SET status='delivered',delivered_at=?,updated_at=?
                   WHERE status='pending' AND event_id IN (
                     SELECT id FROM events WHERE job_id=? AND event='attempt.finished'
                   )""",
                (_now(), _now(), row["id"]),
            )
            claimed.append(
                {
                    "row": dict(row),
                    "number": number,
                    "project": project,
                    "runtime": runtime,
                    "logPath": log_path,
                    "reportPath": report_path,
                    "inputPath": input_path,
                    "reason": reason,
                }
            )
        db.execute("COMMIT")
    return claimed


def _snapshot(item: dict[str, Any]) -> dict[str, Any]:
    row = item["row"]
    project = item["project"]
    manifest_path = project / ".gamewiki" / "manifest.json"
    manifest = read_json(manifest_path) if manifest_path.is_file() else {}
    config = json.loads(row.get("config_json") or "{}")
    return {
        "job": {
            "id": row["id"],
            "game": row["game"],
            "slug": row["slug"],
            "status": row["status"],
            "stage": row["current_stage"],
            "attempts": row["attempts"],
            "maxAttempts": row["max_attempts"],
            "logPath": row["log_path"],
        },
        "config": {
            key: config.get(key)
            for key in ("game", "platform", "officialUrl", "siteUrl", "publish", "manualKeywords")
            if key in config
        },
        "project": {
            "root": str(project),
            "manifestPath": str(manifest_path),
            "manifestStatus": manifest.get("status"),
            "manifestStages": manifest.get("stages"),
            "currentAttempt": manifest.get("currentAttempt"),
        },
        "lastError": _redact(str(row.get("last_error") or ""), limit=4000),
        "jobLogTail": _read_tail(row.get("log_path"), limit=20000),
        "agent2": {
            "run": item["number"],
            "reason": item["reason"],
            "rules": [
                "Repair only this game project workspace.",
                "Do not edit Factory source, systemd units, secrets, Git remotes, or production env files.",
                "Do not run git push or Cloudflare/GitHub publishing commands; Worker owns retry and publish.",
                "Do not use refresh, recluster, overwrite, or any other option that repeats paid stages unless the input explicitly says it is a no-cost local verification.",
                "If the issue is credentials, quota, permissions, schema, template/core Factory code, DNS, or account state, return escalate.",
            ],
        },
    }


def _prompt(input_path: Path) -> str:
    return f"""
You are Agent2, the server-side Game Wiki Factory recovery controller.

Read the recovery input JSON at:
{input_path}

Your job is to repair exactly one failed Game Wiki job when the issue is a bounded
single-project problem. Work inside the current game project only.

Allowed actions:
- inspect .gamewiki/manifest.json, intake/, content/, package scripts, and local logs;
- make minimal edits to this game's deployable project or its .gamewiki checkpoint when that repairs article metadata, MDX formatting, duplicate title/description, slug/directory mismatch, missing generated intake file that can be derived from existing manifest/intake, or a transient publish retry condition;
- run local no-refresh validation such as npm scripts, node checks, TypeScript, or content checks when available.

Forbidden actions:
- do not edit /srv/game-wiki-factory/app or the Factory repository;
- do not read, print, copy, or write .env/factory.env/secrets;
- do not run git push, gh repo edits, Cloudflare Pages publish commands, or gamewiki.py jobs retry;
- do not use refresh/recluster/overwrite flags or repeat paid Basic Info, Guide Search, article generation, or translation stages;
- do not change GitHub repository visibility or Cloudflare credentials.

The parent controller will read your final JSON and, when appropriate, put the
same Job ID back into retry_wait so Worker can continue and publish. Return
"repaired" only if you changed files and performed reasonable local checks.
Return "retry_without_changes" only for transient external failures where the
existing checkpoint is enough. Return "escalate" for Factory source bugs,
permissions, quota, DNS, missing credentials, ambiguous game identity, unsafe
workspace state, or anything outside the rules.
""".strip()


SAFE_CODEX_CHILD_ENV_NAMES = {
    "ALLUSERSPROFILE",
    "APPDATA",
    "CODEX_HOME",
    "COMSPEC",
    "HOME",
    "HOMEDRIVE",
    "HOMEPATH",
    "LANG",
    "LC_ALL",
    "LOCALAPPDATA",
    "LOGNAME",
    "PATH",
    "PATHEXT",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "PROGRAMW6432",
    "SHELL",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TERM",
    "TMP",
    "USER",
    "USERDOMAIN",
    "USERNAME",
    "USERPROFILE",
    "WINDIR",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
}

AGENT2_CONFIG_NAMES = {
    "GAMEWIKI_AGENT2_OPENAI_API_KEY",
    "codex_cli_api_key",
    "GAMEWIKI_AGENT2_OPENAI_BASE_URL",
    "base_url",
    "GAMEWIKI_AGENT2_CODEX_WIRE_API",
    "GAMEWIKI_AGENT2_REQUIRES_OPENAI_AUTH",
    "GAMEWIKI_AGENT2_CODEX_MODEL",
    "model",
    "GAMEWIKI_AGENT2_CODEX_REASONING_EFFORT",
    "model_reasoning_effort",
    "GAMEWIKI_AGENT2_DISABLE_RESPONSE_STORAGE",
    "disable_response_storage",
}


def _agent2_config(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Read only Agent2-specific settings without inheriting Factory secrets."""
    source = dict(base_env if base_env is not None else os.environ)
    config: dict[str, str] = {}
    env_file = ROOT / ".env"
    if env_file.is_file():
        for key, value in parse_dotenv(env_file).items():
            if key in AGENT2_CONFIG_NAMES:
                config[key] = value
    for key, value in source.items():
        if key in AGENT2_CONFIG_NAMES:
            config[key] = value
    return config


def _codex_child_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    source = dict(base_env if base_env is not None else os.environ)
    config = _agent2_config(source)
    env = {
        key: value
        for key, value in source.items()
        if key.upper() in SAFE_CODEX_CHILD_ENV_NAMES
    }
    env.setdefault("PYTHONIOENCODING", "utf-8")
    api_key = (
        config.get("GAMEWIKI_AGENT2_OPENAI_API_KEY", "").strip()
        or config.get("codex_cli_api_key", "").strip()
    )
    if api_key:
        # This is the only secret intentionally given to Agent2.  Factory
        # provider, GitHub, Cloudflare, notification, and control-plane
        # credentials stay out of the child process environment.
        env["CODEX_API_KEY"] = api_key
        env["OPENAI_API_KEY"] = api_key
    base_url = (
        config.get("GAMEWIKI_AGENT2_OPENAI_BASE_URL", "").strip()
        or config.get("base_url", "").strip()
    )
    if base_url:
        env["OPENAI_BASE_URL"] = base_url
        env["GAMEWIKI_AGENT2_OPENAI_BASE_URL"] = base_url
    for key in (
        "GAMEWIKI_AGENT2_CODEX_WIRE_API",
        "GAMEWIKI_AGENT2_REQUIRES_OPENAI_AUTH",
        "GAMEWIKI_AGENT2_CODEX_MODEL",
        "model",
        "GAMEWIKI_AGENT2_CODEX_REASONING_EFFORT",
        "model_reasoning_effort",
        "GAMEWIKI_AGENT2_DISABLE_RESPONSE_STORAGE",
        "disable_response_storage",
    ):
        if config.get(key, "").strip():
            env[key] = config[key]
    return env


def _toml_string(value: str) -> str:
    return json.dumps(value)


def _codex_command(project: Path, report_path: Path, env: dict[str, str]) -> list[str]:
    custom = os.environ.get("GAMEWIKI_AGENT2_CODEX_COMMAND_JSON", "").strip()
    if custom:
        parsed = json.loads(custom)
        if not isinstance(parsed, list) or not all(isinstance(part, str) for part in parsed):
            raise ValueError("GAMEWIKI_AGENT2_CODEX_COMMAND_JSON must be a JSON string array")
        replacements = {
            "{project}": str(project),
            "{report}": str(report_path),
            "{schema}": str(ROOT / "schemas" / "agent2-recovery-report.schema.json"),
        }
        return [replacements.get(part, part) for part in parsed]
    command = [
        os.environ.get("GAMEWIKI_AGENT2_CODEX_BIN", "codex"),
        "exec",
        "--cd",
        str(project),
        "--skip-git-repo-check",
        "--sandbox",
        os.environ.get("GAMEWIKI_AGENT2_SANDBOX", "workspace-write"),
        "--config",
        'approval_policy="never"',
        "--output-schema",
        str(ROOT / "schemas" / "agent2-recovery-report.schema.json"),
        "--output-last-message",
        str(report_path),
        "--color",
        "never",
    ]
    base_url = (
        os.environ.get("GAMEWIKI_AGENT2_OPENAI_BASE_URL", "").strip()
        or env.get("GAMEWIKI_AGENT2_OPENAI_BASE_URL", "").strip()
        or env.get("base_url", "").strip()
    )
    if base_url:
        provider = os.environ.get("GAMEWIKI_AGENT2_CODEX_PROVIDER", "").strip() or "agent2_proxy"
        wire_api = (
            os.environ.get("GAMEWIKI_AGENT2_CODEX_WIRE_API", "").strip()
            or env.get("GAMEWIKI_AGENT2_CODEX_WIRE_API", "").strip()
            or env.get("wire_api", "").strip()
            or "responses"
        )
        command.extend(
            [
                "--config",
                f"model_provider={_toml_string(provider)}",
                "--config",
                f"model_providers.{provider}.name={_toml_string('Agent2 configured provider')}",
                "--config",
                f"model_providers.{provider}.base_url={_toml_string(base_url)}",
                "--config",
                f"model_providers.{provider}.env_key={_toml_string('CODEX_API_KEY')}",
                "--config",
                f"model_providers.{provider}.wire_api={_toml_string(wire_api)}",
            ]
        )
        requires_openai_auth = (
            os.environ.get("GAMEWIKI_AGENT2_REQUIRES_OPENAI_AUTH", "").strip()
            or env.get("GAMEWIKI_AGENT2_REQUIRES_OPENAI_AUTH", "").strip()
            or env.get("requires_openai_auth", "").strip()
        )
        if requires_openai_auth:
            command.extend(
                [
                    "--config",
                    f"model_providers.{provider}.requires_openai_auth="
                    f"{'true' if requires_openai_auth.casefold() in {'1', 'true', 'yes', 'on'} else 'false'}",
                ]
            )
    model = os.environ.get("GAMEWIKI_AGENT2_CODEX_MODEL", "").strip() or env.get("model", "").strip()
    if model:
        command.extend(["--model", model])
    reasoning = (
        os.environ.get("GAMEWIKI_AGENT2_CODEX_REASONING_EFFORT", "").strip()
        or env.get("model_reasoning_effort", "").strip()
    )
    if reasoning:
        command.extend(["--config", f"model_reasoning_effort={_toml_string(reasoning)}"])
    disable_storage = env.get("GAMEWIKI_AGENT2_DISABLE_RESPONSE_STORAGE", "").strip() or env.get("disable_response_storage", "").strip()
    if disable_storage.casefold() in {"1", "true", "yes", "on"}:
        command.extend(["--config", "disable_response_storage=true"])
    command.append("-")
    return command


def _run_codex(item: dict[str, Any]) -> tuple[int, dict[str, Any] | None, str | None]:
    snapshot = _snapshot(item)
    write_json(item["inputPath"], snapshot)
    project_input = item["project"] / ".gamewiki" / "agent2" / "input.json"
    project_input.parent.mkdir(parents=True, exist_ok=True)
    write_json(project_input, snapshot)
    prompt = _prompt(project_input)
    env = _codex_child_env()
    command = _codex_command(item["project"], item["reportPath"], env)
    timeout = max(60, int(os.environ.get("GAMEWIKI_AGENT2_CODEX_TIMEOUT_SECONDS", str(DEFAULT_CODEX_TIMEOUT_SECONDS))))
    with item["logPath"].open("w", encoding="utf-8") as log:
        log.write(f"job={item['row']['id']}\nrun={item['number']}\nstarted={_now()}\n")
        log.write("command=" + subprocess.list2cmdline(command) + "\n")
        try:
            completed = subprocess.run(
                command,
                cwd=item["project"],
                env=env,
                input=prompt,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            log.write(_redact(completed.stdout or "", limit=60000))
            log.write(f"\nfinished={_now()}\nexitCode={completed.returncode}\n")
            code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or ""
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            log.write(_redact(str(output), limit=60000))
            log.write(f"\nfinished={_now()}\nexitCode=124\n")
            return 124, None, "Codex CLI timed out"
    if not item["reportPath"].is_file():
        return code, None, "Codex CLI did not write a report"
    try:
        report = read_json(item["reportPath"])
    except (OSError, ValueError, RuntimeError) as exc:
        return code, None, f"Could not read Codex report: {exc}"
    return code, report, None


def _finish(
    item: dict[str, Any],
    *,
    status: str,
    action: str,
    report: dict[str, Any] | None,
    error: str | None = None,
) -> None:
    row = item["row"]
    now = _now()
    with connect() as db:
        _ensure_schema(db)
        db.execute(
            """UPDATE agent2_runs SET status=?,finished_at=?,action=?,last_error=?
               WHERE job_id=? AND number=?""",
            (status, now, action, error, row["id"], item["number"]),
        )
        if action in {"repaired", "retry_without_changes"} and status == "succeeded":
            db.execute(
                """UPDATE jobs SET status='retry_wait',available_at=?,last_error=NULL,
                          finished_at=NULL,result_json=NULL,lease_owner=NULL,lease_expires_at=NULL,
                          updated_at=?
                   WHERE id=? AND status='agent_repair'""",
                (now, now, row["id"]),
            )
            _event(
                db,
                row["id"],
                "job.agent2_requeued",
                run=item["number"],
                action=action,
                summary=(report or {}).get("summary"),
                filesChanged=(report or {}).get("filesChanged") or [],
                verification=(report or {}).get("verification") or [],
            )
            return
        original = row["status"] if row["status"] in {"needs_attention", "failed"} else "needs_attention"
        detail = {
            "run": item["number"],
            "action": action,
            "summary": (report or {}).get("summary"),
            "escalationReason": (report or {}).get("escalationReason") or error,
        }
        db.execute(
            """UPDATE jobs SET status=?,last_error=COALESCE(?,last_error),updated_at=?
               WHERE id=? AND status='agent_repair'""",
            (original, error, now, row["id"]),
        )
        _event(db, row["id"], "job.agent2_escalated", notify=True, **detail)


def _dry_run(limit: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    max_runs = max(0, int(os.environ.get("GAMEWIKI_AGENT2_MAX_RUNS", "2")))
    with connect() as db:
        _ensure_schema(db)
        rows = db.execute(
            """SELECT * FROM jobs
               WHERE status IN ('needs_attention','failed') AND cancel_requested=0
               ORDER BY updated_at LIMIT ?""",
            (max(1, min(limit, 50)),),
        ).fetchall()
        for row in rows:
            eligible, reason = _is_eligible(row)
            if not eligible:
                continue
            if _run_count(db, row["id"]) >= max_runs:
                continue
            if _safe_project_dir(row["slug"]) is None:
                continue
            results.append(
                {
                    "jobId": row["id"],
                    "game": row["game"],
                    "stage": row["current_stage"],
                    "reason": reason,
                }
            )
            if len(results) >= limit:
                break
    return results


def should_defer_operator_notification(job_id: str, event: str) -> bool:
    """Let Agent2 try bounded worker failures before notifying the operator.

    Only the worker's raw attempt failure notification is deferred. Agent2's
    own escalation notification must still be delivered, otherwise a failed
    repair attempt would become silent.
    """
    if event != "attempt.finished":
        return False
    if os.environ.get("GAMEWIKI_AGENT2_ENABLED", "1").strip().casefold() in {"0", "false", "no", "off"}:
        return False
    max_runs = max(0, int(os.environ.get("GAMEWIKI_AGENT2_MAX_RUNS", "2")))
    if max_runs <= 0:
        return False
    with connect() as db:
        _ensure_schema(db)
        row = db.execute(
            "SELECT * FROM jobs WHERE id=? AND status IN ('needs_attention','failed') AND cancel_requested=0",
            (job_id,),
        ).fetchone()
        if not row:
            return False
        eligible, _reason = _is_eligible(row)
        if not eligible:
            return False
        if _run_count(db, job_id) >= max_runs:
            return False
        slug = row["slug"]
    return _safe_project_dir(slug) is not None


def recover_once(*, dry_run: bool = False, limit: int = 3) -> list[dict[str, Any]]:
    if os.environ.get("GAMEWIKI_AGENT2_ENABLED", "1").strip().casefold() in {"0", "false", "no", "off"}:
        return []
    if dry_run:
        return _dry_run(limit)
    candidates = _claim(limit)
    results: list[dict[str, Any]] = []
    for item in candidates:
        row = item["row"]
        code, report, error = _run_codex(item)
        action = str((report or {}).get("status") or "escalate")
        if code != 0 and action not in {"repaired", "retry_without_changes"}:
            error = error or f"Codex CLI exited {code}"
            _finish(item, status="failed", action="codex_failed", report=report, error=error)
            results.append({"jobId": row["id"], "game": row["game"], "status": "escalated", "error": error})
            continue
        if action not in {"repaired", "retry_without_changes", "escalate", "no_action"}:
            error = f"Unexpected Agent2 report status: {action}"
            _finish(item, status="failed", action="invalid_report", report=report, error=error)
            results.append({"jobId": row["id"], "game": row["game"], "status": "escalated", "error": error})
            continue
        final_status = "succeeded" if action in {"repaired", "retry_without_changes"} else "escalated"
        _finish(item, status=final_status, action=action, report=report, error=error)
        results.append({"jobId": row["id"], "game": row["game"], "status": final_status, "action": action})
    return results


def agent2_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gamewiki.py agent2")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    args = parser.parse_args(argv)
    if args.once:
        recovered = recover_once(dry_run=args.dry_run, limit=args.limit)
        print(json.dumps({"dryRun": args.dry_run, "agent2": recovered}, ensure_ascii=False, indent=2))
        return 0
    while True:
        recovered = recover_once(dry_run=args.dry_run, limit=args.limit)
        print(json.dumps({"timestamp": _now(), "dryRun": args.dry_run, "agent2": recovered}, ensure_ascii=False))
        time.sleep(max(10.0, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(agent2_cli(sys.argv[1:]))
