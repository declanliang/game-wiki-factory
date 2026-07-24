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
        hosting = result.get("hosting") or {}
        if hosting.get("status") == "awaiting_domain_configuration":
            lines.append("发布：Private GitHub 和 Cloudflare Pages 部署已完成，NEXT_PUBLIC_SITE_URL 已设置；请绑定自定义域名后执行最终线上验收。")
        elif hosting.get("status") == "complete":
            lines.append("发布：Cloudflare Pages 部署与线上验收已完成。")
        elif hosting.get("status") == "manual_action_required":
            lines.append("发布：Cloudflare 自动发布被显式跳过，需要运营者手工完成 Pages 部署。")
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


def cancelled_batch_message(items: list[dict[str, Any]]) -> str:
    """Summarize a batch pause/cancel instead of sending one message per job."""
    games = [str(item["game"]) for item in items]
    shown = games[:8]
    suffix = f"，另 {len(games) - len(shown)} 个" if len(games) > len(shown) else ""
    return "\n".join([
        "⛔ Game Wiki 批量任务已取消",
        f"数量：{len(games)}",
        f"游戏：{'、'.join(shown)}{suffix}",
        "处理：任务 checkpoint 已保留；恢复时请重新入队，而不是重新生成。",
    ])


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
    # Fetch enough rows to collapse a whole operator-initiated cancellation
    # batch even when it is larger than the normal per-tick notification limit.
    items = pending_notifications(max(limit, 1000))
    groups: list[list[dict[str, Any]]] = []
    cancelled = [item for item in items if item["event_status"] == "cancelled"]
    if cancelled:
        groups.append(cancelled)
    groups.extend([[item] for item in items if item["event_status"] != "cancelled"])
    for group in groups:
        message = cancelled_batch_message(group) if len(group) > 1 else notification_message(group[0])
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
            acknowledge_notifications([int(item["notification_id"]) for item in group])
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            failures += 1
            for item in group:
                defer_notification(int(item["notification_id"]), str(exc))
            print(
                f"notification group {[item['notification_id'] for item in group]} delivery failed: {exc}",
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
