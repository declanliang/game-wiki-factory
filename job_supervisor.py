"""Deterministic recovery policy for checkpoint-safe background job failures."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from typing import Any

from job_system import _event, _now, connect, data_dir


SAFE_RECOVERY_PATTERNS = (
    "article generation failed for",
    "translation failed for",
    "no incomplete response was accepted",
    "existing valid locale checkpoints were preserved",
)

BLOCKED_RECOVERY_PATTERNS = (
    "api key",
    "unauthorized",
    "forbidden",
    "insufficient",
    "quota",
    "balance",
    "permission",
    "schema",
    "identity",
    "candidate",
    "too close to select safely",
    "official url",
    "github repository visibility",
    "secret-like",
)


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _recovery_count(db, job_id: str) -> int:
    return int(
        db.execute(
            "SELECT COUNT(*) FROM events WHERE job_id=? AND event='job.supervisor_requeued'",
            (job_id,),
        ).fetchone()[0]
    )


def _is_checkpoint_safe(job: dict[str, Any]) -> bool:
    if str(job.get("task_type") or "site") != "site":
        return False
    if str(job.get("current_stage") or "") not in {"articles", "pipeline"}:
        return False
    error = str(job.get("last_error") or "").casefold()
    if any(pattern in error for pattern in BLOCKED_RECOVERY_PATTERNS):
        return False
    return any(pattern in error for pattern in SAFE_RECOVERY_PATTERNS)


def recover_once(*, dry_run: bool = False, limit: int = 20) -> list[dict[str, Any]]:
    """Requeue only failures whose own exception promises valid checkpoint reuse."""
    usage = shutil.disk_usage(data_dir())
    used_percent = (usage.used / usage.total) * 100 if usage.total else 0
    pause_percent = float(os.environ.get("GAMEWIKI_DISK_PAUSE_PERCENT", "90"))
    if used_percent >= pause_percent:
        return []

    max_recoveries = max(0, int(os.environ.get("GAMEWIKI_SUPERVISOR_MAX_RECOVERIES", "6")))
    cooldown_seconds = max(0, int(os.environ.get("GAMEWIKI_SUPERVISOR_COOLDOWN_SECONDS", "300")))
    now = datetime.now(timezone.utc)
    recovered: list[dict[str, Any]] = []
    with connect() as db:
        rows = db.execute(
            """SELECT id,game,slug,status,current_stage,last_error,finished_at,config_json
               FROM jobs
               WHERE status IN ('needs_attention','failed') AND cancel_requested=0
               ORDER BY updated_at LIMIT ?""",
            (max(1, min(limit, 200)),),
        ).fetchall()
        for row in rows:
            item = dict(row)
            config = json.loads(item.pop("config_json") or "{}")
            item["task_type"] = str(config.get("taskType") or "site")
            if not _is_checkpoint_safe(item):
                continue
            recoveries = _recovery_count(db, item["id"])
            if recoveries >= max_recoveries:
                continue
            finished_at = item.get("finished_at")
            available = (
                _parse_time(finished_at) + timedelta(seconds=cooldown_seconds)
                if finished_at
                else now
            )
            if available > now:
                continue
            recovery = {
                "jobId": item["id"],
                "game": item["game"],
                "stage": item["current_stage"],
                "recovery": recoveries + 1,
                "maxRecoveries": max_recoveries,
            }
            recovered.append(recovery)
            if dry_run:
                continue
            changed = db.execute(
                """UPDATE jobs SET status='retry_wait',available_at=?,finished_at=NULL,
                          last_error=NULL,lease_owner=NULL,lease_expires_at=NULL,updated_at=?
                   WHERE id=? AND status IN ('needs_attention','failed') AND cancel_requested=0""",
                (_now(), _now(), item["id"]),
            ).rowcount
            if not changed:
                continue
            _event(
                db,
                item["id"],
                "job.supervisor_requeued",
                recovery=recoveries + 1,
                policy="checkpoint_safe_content_retry",
            )
            # A terminal notification may have been created milliseconds before
            # this timer ran. Suppress it only after the job was safely requeued;
            # the eventual success or exhausted-recovery event remains durable.
            db.execute(
                """UPDATE notifications SET status='delivered',delivered_at=?,updated_at=?
                   WHERE status='pending' AND event_id IN (
                     SELECT id FROM events WHERE job_id=? AND event='attempt.finished'
                   )""",
                (_now(), _now(), item["id"]),
            )
    return recovered


def supervisor_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gamewiki.py supervisor")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    recovered = recover_once(dry_run=args.dry_run, limit=args.limit)
    print(json.dumps({"dryRun": args.dry_run, "recovered": recovered}, ensure_ascii=False, indent=2))
    return 0
