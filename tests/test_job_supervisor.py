import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_supervisor import recover_once
from job_system import _event, connect, pending_notifications, submit


class JobSupervisorTests(unittest.TestCase):
    def test_structured_524_is_safe_despite_candidate_traceback_name(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "GAMEWIKI_DATA_DIR": temporary,
                "GAMEWIKI_DISK_PAUSE_PERCENT": "100",
                "GAMEWIKI_SUPERVISOR_COOLDOWN_SECONDS": "0",
            },
        ):
            job_id = self._failed_job(
                temporary,
                'cluster_candidates: {"status":524,"error_code":524,'
                '"error_name":"origin_response_timeout"}',
                stage="gameProfile",
            )
            recovered = recover_once()
            with connect() as db:
                status = db.execute(
                    "SELECT status FROM jobs WHERE id=?", (job_id,)
                ).fetchone()[0]
        self.assertEqual([item["jobId"] for item in recovered], [job_id])
        self.assertEqual(status, "retry_wait")

    def _failed_job(self, temporary: str, error: str, stage: str = "articles") -> str:
        config = Path(temporary) / "job.json"
        config.write_text(json.dumps({"game": "Retry Game", "platform": "roblox"}), encoding="utf-8")
        job_id = submit(config)
        with connect() as db:
            db.execute(
                """UPDATE jobs SET status='needs_attention',current_stage=?,last_error=?,
                          finished_at='2020-01-01T00:00:00+00:00' WHERE id=?""",
                (stage, error, job_id),
            )
            _event(
                db,
                job_id,
                "attempt.finished",
                notify=True,
                status="needs_attention",
                errorClass="needs_attention",
            )
        return job_id

    def test_requeues_checkpoint_safe_translation_failure_and_suppresses_noise(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "GAMEWIKI_DATA_DIR": temporary,
                "GAMEWIKI_DISK_PAUSE_PERCENT": "100",
                "GAMEWIKI_SUPERVISOR_COOLDOWN_SECONDS": "0",
            },
        ):
            job_id = self._failed_job(
                temporary,
                "Translation failed for 7 item(s); existing valid locale checkpoints were preserved.",
            )
            recovered = recover_once()
            self.assertEqual([item["jobId"] for item in recovered], [job_id])
            with connect() as db:
                job = db.execute("SELECT status,last_error,finished_at FROM jobs WHERE id=?", (job_id,)).fetchone()
                events = db.execute(
                    "SELECT COUNT(*) FROM events WHERE job_id=? AND event='job.supervisor_requeued'",
                    (job_id,),
                ).fetchone()[0]
            self.assertEqual(job["status"], "retry_wait")
            self.assertIsNone(job["last_error"])
            self.assertIsNone(job["finished_at"])
            self.assertEqual(events, 1)
            self.assertEqual(pending_notifications(), [])

    def test_requeues_malformed_context_response_before_content_generation(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "GAMEWIKI_DATA_DIR": temporary,
                "GAMEWIKI_DISK_PAUSE_PERCENT": "100",
                "GAMEWIKI_SUPERVISOR_COOLDOWN_SECONDS": "0",
            },
        ):
            job_id = self._failed_job(
                temporary,
                "json.decoder.JSONDecodeError: Expecting ',' delimiter: line 1 column 120",
                stage="gameProfile",
            )
            recovered = recover_once()
            self.assertEqual([item["jobId"] for item in recovered], [job_id])
            with connect() as db:
                status = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
            self.assertEqual(status, "retry_wait")

    def test_requeues_checkpoint_safe_provider_524_failure(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "GAMEWIKI_DATA_DIR": temporary,
                "GAMEWIKI_DISK_PAUSE_PERCENT": "100",
                "GAMEWIKI_SUPERVISOR_COOLDOWN_SECONDS": "0",
            },
        ):
            job_id = self._failed_job(
                temporary,
                "API 524 for article generation; valid checkpoints remain on disk",
            )
            self.assertEqual([item["jobId"] for item in recover_once()], [job_id])

    def test_does_not_requeue_identity_or_unknown_failures(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "GAMEWIKI_DATA_DIR": temporary,
                "GAMEWIKI_DISK_PAUSE_PERCENT": "100",
                "GAMEWIKI_SUPERVISOR_COOLDOWN_SECONDS": "0",
            },
        ):
            identity = self._failed_job(temporary, "Two Roblox candidates are too close to select safely")
            unknown = self._failed_job(temporary, "unknown production build problem", stage="site")
            self.assertEqual(recover_once(), [])
            with connect() as db:
                statuses = {
                    row["id"]: row["status"]
                    for row in db.execute("SELECT id,status FROM jobs WHERE id IN (?,?)", (identity, unknown))
                }
            self.assertEqual(statuses[identity], "needs_attention")
            self.assertEqual(statuses[unknown], "needs_attention")

    def test_does_not_requeue_quota_failure_even_with_checkpoint_text(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "GAMEWIKI_DATA_DIR": temporary,
                "GAMEWIKI_DISK_PAUSE_PERCENT": "100",
                "GAMEWIKI_SUPERVISOR_COOLDOWN_SECONDS": "0",
            },
        ):
            job_id = self._failed_job(
                temporary,
                "Translation failed for 7 item(s); existing valid locale checkpoints were preserved; insufficient_user_quota.",
            )
            self.assertEqual(recover_once(), [])
            with connect() as db:
                status = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
            self.assertEqual(status, "needs_attention")
            self.assertEqual(len(pending_notifications()), 1)

    def test_stops_after_recovery_budget(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "GAMEWIKI_DATA_DIR": temporary,
                "GAMEWIKI_DISK_PAUSE_PERCENT": "100",
                "GAMEWIKI_SUPERVISOR_COOLDOWN_SECONDS": "0",
                "GAMEWIKI_SUPERVISOR_MAX_RECOVERIES": "1",
            },
        ):
            job_id = self._failed_job(temporary, "Article generation failed for 2 item(s); no incomplete response was accepted.")
            with connect() as db:
                _event(db, job_id, "job.supervisor_requeued", recovery=1)
            self.assertEqual(recover_once(), [])


if __name__ == "__main__":
    unittest.main()
