from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_notifier import dispatch_once, notification_message
from job_system import _event, connect, pending_notifications, submit


class JobNotifierTests(unittest.TestCase):
    def _notification(
        self,
        temporary: str,
        status: str = "needs_attention",
        error_class: str | None = None,
        **detail,
    ) -> dict:
        config = Path(temporary) / "game.json"
        config.write_text(json.dumps({"game": "Notify Game"}), encoding="utf-8")
        job_id = submit(config)
        with connect() as db:
            db.execute(
                "UPDATE jobs SET status=?,current_stage='articles',attempts=2 WHERE id=?",
                (status, job_id),
            )
            _event(
                db,
                job_id,
                "attempt.finished",
                notify=True,
                attempt=2,
                status=status,
                errorClass=error_class or status,
                **detail,
            )
        return pending_notifications()[0]

    def test_attention_message_escalates_instead_of_promising_agent_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"GAMEWIKI_DATA_DIR": temporary}
        ):
            message = notification_message(self._notification(temporary))
        self.assertIn("交给 Codex", message)
        self.assertIn("Notify Game", message)

    def test_quota_message_demands_immediate_operator_action(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"GAMEWIKI_DATA_DIR": temporary}
        ):
            message = notification_message(
                self._notification(
                    temporary,
                    error_class="quota_exhausted",
                    quotaProvider={
                        "id": "llm",
                        "label": "LLM 内容生成/翻译 API",
                        "credential": "LLM_API_KEY_1..N",
                        "endpoint": "api.example.test",
                    },
                    pausedJobs=12,
                )
            )
        self.assertIn("LLM 内容生成/翻译 API（api.example.test）", message)
        self.assertIn("LLM_API_KEY_1..N", message)
        self.assertIn("已暂停 12 个", message)
        self.assertIn("不再逐任务发送额度告警", message)
        self.assertIn("重试本条 Job ID", message)

    def test_success_message_calls_out_cloudflare_domain_handoff(self) -> None:
        item = {
            "event_status": "succeeded",
            "game": "Published Game",
            "job_id": "job-1",
            "current_stage": "complete",
            "job_attempts": 1,
            "max_attempts": 4,
            "result": {
                "articles": {"english": 8, "allLanguages": 40},
                "hosting": {"provider": "cloudflare-pages", "status": "awaiting_domain_configuration"},
            },
        }
        message = notification_message(item)
        self.assertIn("Cloudflare Pages 部署已完成", message)
        self.assertIn("NEXT_PUBLIC_SITE_URL 已设置", message)

    def test_successful_delivery_acknowledges_outbox_row(self) -> None:
        env = {
            "GAMEWIKI_DATA_DIR": "",
            "GAMEWIKI_NOTIFICATION_COMMAND_JSON": json.dumps(
                ["sender", "--message", "{message}"]
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            env["GAMEWIKI_DATA_DIR"] = temporary
            with patch.dict(os.environ, env), patch(
                "job_notifier.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "ok", ""),
            ) as run:
                self._notification(temporary)
                self.assertEqual(dispatch_once(), 0)
                self.assertEqual(pending_notifications(), [])
                self.assertIn("Notify Game", run.call_args.args[0][-1])

    def test_failed_delivery_is_deferred_without_acknowledgement(self) -> None:
        env = {
            "GAMEWIKI_DATA_DIR": "",
            "GAMEWIKI_NOTIFICATION_COMMAND_JSON": json.dumps(
                ["sender", "--message", "{message}"]
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            env["GAMEWIKI_DATA_DIR"] = temporary
            with patch.dict(os.environ, env), patch(
                "job_notifier.subprocess.run",
                return_value=subprocess.CompletedProcess([], 1, "", "offline"),
            ):
                item = self._notification(temporary)
                self.assertEqual(dispatch_once(), 1)
                with connect() as db:
                    row = db.execute(
                        "SELECT status,attempts,delivered_at FROM notifications WHERE id=?",
                        (item["notification_id"],),
                    ).fetchone()
                self.assertEqual(row["status"], "pending")
                self.assertEqual(row["attempts"], 1)
                self.assertIsNone(row["delivered_at"])

    def test_agent2_eligible_attempt_failure_is_not_sent_before_repair(self) -> None:
        env = {
            "GAMEWIKI_DATA_DIR": "",
            "GAMEWIKI_PROJECTS_ROOT": "",
            "GAMEWIKI_NOTIFICATION_COMMAND_JSON": json.dumps(
                ["sender", "--message", "{message}"]
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            env["GAMEWIKI_DATA_DIR"] = str(Path(temporary) / "data")
            env["GAMEWIKI_PROJECTS_ROOT"] = str(Path(temporary) / "projects")
            project = Path(env["GAMEWIKI_PROJECTS_ROOT"]) / "notify-game"
            (project / ".gamewiki").mkdir(parents=True)
            with patch.dict(os.environ, env), patch(
                "job_notifier.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "ok", ""),
            ) as run:
                config = Path(temporary) / "game.json"
                config.write_text(json.dumps({"game": "Notify Game"}), encoding="utf-8")
                job_id = submit(config)
                with connect() as db:
                    db.execute(
                        """UPDATE jobs SET status='failed',current_stage='pipeline',
                                  attempts=4,last_error='ToAPIs returned HTTP 524'
                           WHERE id=?""",
                        (job_id,),
                    )
                    _event(db, job_id, "attempt.finished", notify=True, status="failed")
                self.assertEqual(dispatch_once(), 0)
                self.assertEqual(run.call_count, 0)
                self.assertEqual(len(pending_notifications()), 1)

    def test_agent2_escalation_is_still_sent(self) -> None:
        env = {
            "GAMEWIKI_DATA_DIR": "",
            "GAMEWIKI_PROJECTS_ROOT": "",
            "GAMEWIKI_NOTIFICATION_COMMAND_JSON": json.dumps(
                ["sender", "--message", "{message}"]
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            env["GAMEWIKI_DATA_DIR"] = str(Path(temporary) / "data")
            env["GAMEWIKI_PROJECTS_ROOT"] = str(Path(temporary) / "projects")
            project = Path(env["GAMEWIKI_PROJECTS_ROOT"]) / "notify-game"
            (project / ".gamewiki").mkdir(parents=True)
            with patch.dict(os.environ, env), patch(
                "job_notifier.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "ok", ""),
            ) as run:
                config = Path(temporary) / "game.json"
                config.write_text(json.dumps({"game": "Notify Game"}), encoding="utf-8")
                job_id = submit(config)
                with connect() as db:
                    db.execute(
                        """UPDATE jobs SET status='failed',current_stage='pipeline',
                                  attempts=4,last_error='ToAPIs returned HTTP 524'
                           WHERE id=?""",
                        (job_id,),
                    )
                    _event(
                        db,
                        job_id,
                        "job.agent2_escalated",
                        notify=True,
                        status="failed",
                        action="codex_failed",
                        escalationReason="Codex CLI did not write a report",
                    )
                self.assertEqual(dispatch_once(), 0)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(pending_notifications(), [])

    def test_cancelled_jobs_are_delivered_as_one_batch_message(self) -> None:
        env = {
            "GAMEWIKI_DATA_DIR": "",
            "GAMEWIKI_NOTIFICATION_COMMAND_JSON": json.dumps(
                ["sender", "--message", "{message}"]
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            env["GAMEWIKI_DATA_DIR"] = temporary
            with patch.dict(os.environ, env), patch(
                "job_notifier.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "ok", ""),
            ) as run:
                config = Path(temporary) / "game.json"
                config.write_text(json.dumps({"game": "First Cancelled"}), encoding="utf-8")
                first = submit(config)
                config.write_text(json.dumps({"game": "Second Cancelled"}), encoding="utf-8")
                second = submit(config)
                with connect() as db:
                    for job_id in (first, second):
                        db.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (job_id,))
                        _event(db, job_id, "job.cancel_requested", notify=True, status="cancelled")
                self.assertEqual(dispatch_once(), 0)
                self.assertEqual(run.call_count, 1)
                message = run.call_args.args[0][-1]
                self.assertIn("批量任务已取消", message)
                self.assertIn("数量：2", message)
                self.assertEqual(pending_notifications(), [])


if __name__ == "__main__":
    unittest.main()
