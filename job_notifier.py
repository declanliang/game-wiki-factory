"""Channel-agnostic durable notification dispatcher."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from typing import Any

from job_system import acknowledge_notifications, defer_notification, pending_notifications


def notification_message(item: dict[str, Any]) -> str:
    status = item["event_status"]
    icon = {
        "succeeded": "✅",
        "needs_attention": "⚠️",
        "failed": "❌",
        "cancelled": "⛔",
    }.get(status, "ℹ️")
    lines = [
        f"{icon} Game Wiki 任务状态：{status}",
        f"游戏：{item['game']}",
        f"Job ID：{item['job_id']}",
        f"阶段：{item.get('current_stage') or '-'}",
        f"尝试：{item.get('job_attempts', 0)}/{item.get('max_attempts', 0)}",
    ]
    if status == "succeeded":
        result = item.get("result") or {}
        articles = result.get("articles") or {}
        if articles:
            lines.append(
                f"文章：英文 {articles.get('english', 0)} / 全语言 {articles.get('allLanguages', 0)}"
            )
        online = result.get("onlineVerification") or {}
        origin = online.get("origin")
        if origin:
            lines.append(f"线上：{origin}")
    elif status in {"needs_attention", "failed"}:
        error_class = str((item.get("detail") or {}).get("errorClass") or "")
        if error_class == "quota_exhausted":
            lines.append("原因：API 额度或账户余额不足。任务已立即停止，且不会自动重试付费阶段。")
            lines.append("处理：请立即充值或更换对应 API Key；完成后重试同一 Job ID 以复用 checkpoint。")
        else:
            lines.append("处理：已停止自动推进，请把此 Job ID 交给 Codex/基础设施维护者。")
        if item.get("log_path"):
            lines.append(f"日志：{item['log_path']}")
    return "\n".join(lines)


def command_from_environment(message: str) -> list[str]:
    raw = os.environ.get("GAMEWIKI_NOTIFICATION_COMMAND_JSON", "").strip()
    if not raw:
        raise ValueError("GAMEWIKI_NOTIFICATION_COMMAND_JSON is not configured")
    command = json.loads(raw)
    if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
        raise ValueError("GAMEWIKI_NOTIFICATION_COMMAND_JSON must be a JSON string array")
    if not any("{message}" in part for part in command):
        raise ValueError("notification command must contain a {message} placeholder")
    return [part.replace("{message}", message) for part in command]


def dispatch_once(*, dry_run: bool = False, limit: int = 20) -> int:
    failures = 0
    for item in pending_notifications(limit):
        message = notification_message(item)
        if dry_run:
            print(message)
            continue
        try:
            command = command_from_environment(message)
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=90,
                check=False,
            )
            if result.returncode != 0:
                error = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
                raise RuntimeError(error)
            acknowledge_notifications([int(item["notification_id"])])
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            failures += 1
            defer_notification(int(item["notification_id"]), str(exc))
            print(
                f"notification {item['notification_id']} delivery failed: {exc}",
                file=__import__("sys").stderr,
            )
    return 1 if failures else 0


def notifier_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gamewiki.py notifier")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    if args.once or args.dry_run:
        return dispatch_once(dry_run=args.dry_run, limit=args.limit)
    while True:
        dispatch_once(limit=args.limit)
        time.sleep(max(5.0, args.interval))
