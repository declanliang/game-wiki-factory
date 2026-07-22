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
    def _notification(self, temporary: str, status: str = "needs_attention") -> dict:
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
                errorClass=status,
            )
        return pending_notifications()[0]

    def test_attention_message_escalates_instead_of_promising_agent_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"GAMEWIKI_DATA_DIR": temporary}
        ):
            message = notification_message(self._notification(temporary))
        self.assertIn("交给 Codex", message)
        self.assertIn("Notify Game", message)

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


if __name__ == "__main__":
    unittest.main()
