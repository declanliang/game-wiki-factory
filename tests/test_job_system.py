from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_system import _completion_result, _event, _execution_config, _new_workspace_conflict, _open_quota_circuit, _prune_success_build_artifacts, _publish_command, _resume_quota_circuit, _schedule_next_locale_release, acknowledge_notifications, checkpoint_safe_content_retry, classify_failure, claim, connect, identify_quota_provider, normalize_config, pending_notifications, retry_job, submit, submit_batch


class JobSystemTests(unittest.TestCase):
    def test_manual_retry_is_claimed_before_untouched_batch_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"GAMEWIKI_DATA_DIR": temporary}
        ):
            config = Path(temporary) / "game.json"
            config.write_text(json.dumps({"game": "Untouched"}), encoding="utf-8")
            untouched = submit(config)
            config.write_text(json.dumps({"game": "Repaired"}), encoding="utf-8")
            repaired = submit(config)
            with connect() as db:
                db.execute(
                    "UPDATE jobs SET status='needs_attention' WHERE id=?",
                    (repaired,),
                )
                result = retry_job(
                    db,
                    db.execute("SELECT * FROM jobs WHERE id=?", (repaired,)).fetchone(),
                )
            claimed = claim("repair-worker")
            self.assertEqual(result["status"], "retry_wait")
            self.assertEqual(claimed["id"], repaired)
            self.assertNotEqual(claimed["id"], untouched)

    def test_new_job_defaults_to_automatic_cloudflare_publish(self) -> None:
        config = normalize_config({
            "game": "Pages Game",
            "siteUrl": "https://pages-game.example",
            "publish": True,
        })
        self.assertEqual(config["publication"], {"skipCloudflare": False})
        command = _publish_command(config, "pages-game")
        self.assertNotIn("--skip-cloudflare", command)
        self.assertNotIn("--skip-vercel", command)
        self.assertEqual(command[-2:], ["--site-url", "https://pages-game.example"])

    def test_cloudflare_publish_can_only_be_skipped_explicitly(self) -> None:
        config = normalize_config({"game": "Manual Pages", "publish": True})
        config["publication"]["skipCloudflare"] = True
        self.assertIn("--skip-cloudflare", _publish_command(config, "manual-pages"))

    def test_new_job_does_not_force_paid_refresh(self) -> None:
        config = normalize_config({"game": "Test Game", "platform": "roblox"})
        self.assertEqual(_execution_config(config, 1)["refresh"], {"basicInfo": False, "keywords": False, "articles": False})
        self.assertEqual(_execution_config(config, 2)["refresh"], {"basicInfo": False, "keywords": False, "articles": False})

    def test_incremental_refresh_is_honored_once_then_resumes(self) -> None:
        config = normalize_config({
            "game": "Growing Game",
            "refresh": {"basicInfo": False, "keywords": True, "articles": False},
        })
        self.assertEqual(_execution_config(config, 1)["refresh"], {
            "basicInfo": False,
            "keywords": True,
            "articles": False,
        })
        self.assertEqual(_execution_config(config, 2)["refresh"], {
            "basicInfo": False,
            "keywords": False,
            "articles": False,
        })

    def test_new_jobs_reject_legacy_rebuild_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "legacy rebuild jobs are no longer accepted"):
            normalize_config({"game": "Old Site", "operation": "rebuild"})

    def test_background_jobs_only_accept_site_tasks(self) -> None:
        with self.assertRaisesRegex(ValueError, "taskType must be site"):
            normalize_config({"taskType": "ads", "game": "Ads Game"})

    def test_manual_keywords_are_normalized_and_preserved_on_retry(self) -> None:
        config = normalize_config({
            "game": "Keyword Game",
            "manualKeywords": [" Keyword Game codes ", "keyword game CODES", "Keyword Game units"],
        })
        self.assertEqual(config["operation"], "new")
        self.assertEqual(config["manualKeywords"], ["Keyword Game codes", "Keyword Game units"])
        self.assertEqual(
            _execution_config(config, 2)["manualKeywords"],
            ["Keyword Game codes", "Keyword Game units"],
        )

    def test_batch_is_validated_then_submitted_as_independent_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"GAMEWIKI_DATA_DIR": temporary}):
            config_path = Path(temporary) / "batch.json"
            config_path.write_text(json.dumps({
                "taskType": "siteBatch",
                "defaults": {"platform": "roblox", "publish": True},
                "games": [{"game": "One"}, {"game": "Two"}],
            }), encoding="utf-8")
            job_ids = submit_batch(config_path)
            self.assertEqual(len(job_ids), 2)
            with connect() as db:
                rows = db.execute("SELECT game,status FROM jobs ORDER BY game").fetchall()
            self.assertEqual([dict(row) for row in rows], [
                {"game": "One", "status": "queued"},
                {"game": "Two", "status": "queued"},
            ])

    def test_failure_classification_is_bounded(self) -> None:
        self.assertEqual(classify_failure("HTTP 503 Service Unavailable"), "retryable")
        self.assertEqual(classify_failure("API 524 upstream timeout"), "retryable")
        self.assertEqual(classify_failure("all_channels_circuit_broken"), "retryable")
        self.assertEqual(classify_failure("insufficient_user_quota"), "quota_exhausted")
        self.assertEqual(classify_failure("account balance exhausted"), "quota_exhausted")
        self.assertEqual(classify_failure("Two Roblox candidates are too close to select safely"), "needs_attention")
        self.assertEqual(classify_failure("unknown build problem"), "needs_attention")
        self.assertEqual(
            classify_failure(
                'cluster_candidates failed: {"status":524,"error_code":524,'
                '"error_name":"origin_response_timeout"}'
            ),
            "retryable",
        )

    def test_quota_provider_identifies_llm_without_exposing_key_values(self) -> None:
        provider = identify_quota_provider(
            "All configured LLM API keys have insufficient quota "
            "(provider=toapis.com; credential=LLM_API_KEY_1..N)"
        )
        self.assertEqual(provider["id"], "llm")
        self.assertEqual(provider["endpoint"], "toapis.com")
        self.assertEqual(provider["credential"], "LLM_API_KEY_1..N")
        self.assertNotIn("secret", json.dumps(provider))

    def test_quota_circuit_pauses_queue_and_resumes_all_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"GAMEWIKI_DATA_DIR": temporary}
        ):
            config = Path(temporary) / "game.json"
            config.write_text(json.dumps({"game": "Quota Primary"}), encoding="utf-8")
            primary = submit(config)
            config.write_text(json.dumps({"game": "Quota Waiting"}), encoding="utf-8")
            waiting = submit(config)
            provider = identify_quota_provider(
                "LLM key slot 1 has insufficient quota provider=api.example.test"
            )
            with connect() as db:
                db.execute("UPDATE jobs SET status='running' WHERE id=?", (primary,))
                is_primary, paused = _open_quota_circuit(db, primary, provider)
                db.execute(
                    "UPDATE jobs SET status='needs_attention',quota_provider=? WHERE id=?",
                    (provider["id"], primary),
                )
                statuses = {
                    row["id"]: row["status"]
                    for row in db.execute("SELECT id,status FROM jobs").fetchall()
                }
                resumed = _resume_quota_circuit(db, provider["id"])
                resumed_statuses = {
                    row["id"]: row["status"]
                    for row in db.execute("SELECT id,status FROM jobs").fetchall()
                }
            self.assertTrue(is_primary)
            self.assertEqual(paused, 1)
            self.assertEqual(statuses[waiting], "quota_wait")
            self.assertEqual(resumed, 2)
            self.assertEqual(resumed_statuses[primary], "queued")
            self.assertEqual(resumed_statuses[waiting], "queued")

    def test_new_submission_waits_behind_open_quota_circuit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"GAMEWIKI_DATA_DIR": temporary}
        ):
            config = Path(temporary) / "game.json"
            config.write_text(json.dumps({"game": "Circuit Source"}), encoding="utf-8")
            source = submit(config)
            provider = identify_quota_provider("DataForSEO insufficient balance")
            with connect() as db:
                db.execute("UPDATE jobs SET status='running' WHERE id=?", (source,))
                _open_quota_circuit(db, source, provider)
            config.write_text(json.dumps({"game": "Later Submission"}), encoding="utf-8")
            later = submit(config)
            with connect() as db:
                row = db.execute(
                    "SELECT status,quota_provider FROM jobs WHERE id=?", (later,)
                ).fetchone()
            self.assertEqual(dict(row), {
                "status": "quota_wait",
                "quota_provider": "dataforseo",
            })

    def test_checkpoint_safe_content_failures_allow_bounded_extra_retries(self) -> None:
        self.assertTrue(checkpoint_safe_content_retry(
            "Translation failed; existing valid locale checkpoints were preserved."
        ))
        self.assertTrue(checkpoint_safe_content_retry(
            "Re-run without --overwrite to retry only the missing articles."
        ))
        self.assertFalse(checkpoint_safe_content_retry("unknown build problem"))

    def test_claim_is_atomic_and_records_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"GAMEWIKI_DATA_DIR": temporary}):
            config_path = Path(temporary) / "game.json"
            config_path.write_text(json.dumps({"game": "Test Game", "platform": "roblox"}), encoding="utf-8")
            job_id = submit(config_path)
            first = claim("worker-one")
            second = claim("worker-two")
            self.assertEqual(first["id"], job_id)
            self.assertEqual(first["attempts"], 1)
            self.assertIsNone(second)
            with connect() as db:
                row = db.execute("SELECT status,lease_owner FROM jobs WHERE id=?", (job_id,)).fetchone()
            self.assertEqual(dict(row), {"status": "running", "lease_owner": "worker-one"})

    def test_due_retry_is_claimed_before_new_queued_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"GAMEWIKI_DATA_DIR": temporary}):
            first = Path(temporary) / "first.json"
            second = Path(temporary) / "second.json"
            first.write_text(json.dumps({"game": "Queued Game"}), encoding="utf-8")
            second.write_text(json.dumps({"game": "Retry Game"}), encoding="utf-8")
            queued_id = submit(first)
            retry_id = submit(second)
            with connect() as db:
                db.execute(
                    "UPDATE jobs SET status='retry_wait',available_at=? WHERE id=?",
                    ("2000-01-01T00:00:00+00:00", retry_id),
                )
            claimed = claim("retry-priority-worker")
            self.assertEqual(claimed["id"], retry_id)
            self.assertNotEqual(claimed["id"], queued_id)

    def test_successful_site_schedules_only_the_next_locale_wave(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"GAMEWIKI_DATA_DIR": temporary}
        ):
            config_path = Path(temporary) / "game.json"
            config_path.write_text(
                json.dumps({"game": "Wave Game", "publish": True}),
                encoding="utf-8",
            )
            job_id = submit(config_path)
            with connect() as db:
                source = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
                release_id = _schedule_next_locale_release(
                    db,
                    source,
                    json.loads(source["config_json"]),
                    {
                        "localePublication": {"publishedLocales": ["en"]},
                        "github": {"repo": "owner/wave-game"},
                        "hosting": {
                            "provider": "cloudflare-pages",
                            "projectName": "wave-game",
                            "siteUrl": "https://wave.example",
                            "pagesOrigin": "https://wave-game.pages.dev",
                        },
                    },
                )
                rows = db.execute(
                    "SELECT id,status,available_at,config_json FROM jobs ORDER BY id"
                ).fetchall()
            self.assertEqual(release_id, f"{job_id}-locale-es")
            self.assertEqual(len(rows), 2)
            release = next(row for row in rows if row["id"] == release_id)
            release_config = json.loads(release["config_json"])
            self.assertEqual(release["status"], "queued")
            self.assertEqual(release_config["taskType"], "localeRelease")
            self.assertEqual(release_config["locale"], "es")
            self.assertEqual(release_config["githubRepo"], "owner/wave-game")

    def test_quota_circuit_does_not_pause_scheduled_locale_releases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"GAMEWIKI_DATA_DIR": temporary}
        ):
            config_path = Path(temporary) / "game.json"
            config_path.write_text(json.dumps({"game": "Quota Source"}), encoding="utf-8")
            source_id = submit(config_path)
            with connect() as db:
                source = db.execute("SELECT * FROM jobs WHERE id=?", (source_id,)).fetchone()
                release_id = _schedule_next_locale_release(
                    db,
                    source,
                    json.loads(source["config_json"]),
                    {
                        "localePublication": {"publishedLocales": ["en"]},
                        "github": {"repo": "owner/quota-source"},
                        "hosting": {
                            "provider": "cloudflare-pages",
                            "projectName": "quota-source",
                            "siteUrl": "https://quota.example",
                            "pagesOrigin": "https://quota-source.pages.dev",
                        },
                    },
                )
                db.execute("UPDATE jobs SET status='running' WHERE id=?", (source_id,))
                provider = identify_quota_provider("DataForSEO insufficient balance")
                _open_quota_circuit(db, source_id, provider)
                release = db.execute(
                    "SELECT status,quota_provider FROM jobs WHERE id=?", (release_id,)
                ).fetchone()
            self.assertEqual(dict(release), {"status": "queued", "quota_provider": None})

    def test_full_build_is_rejected_for_new_jobs(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown config field"):
            normalize_config({"game": "Old Site", "fullBuild": True})

    def test_new_job_requires_empty_workspace_but_retry_can_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"GAMEWIKI_PROJECTS_ROOT": temporary}):
            project = Path(temporary) / "new-site"
            project.mkdir()
            self.assertEqual(_new_workspace_conflict("new-site", 1), project)
            self.assertIsNone(_new_workspace_conflict("new-site", 2))

    def test_successful_published_job_prunes_only_reproducible_build_caches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {"GAMEWIKI_PROJECTS_ROOT": temporary, "GAMEWIKI_PRUNE_SUCCESS_BUILD_ARTIFACTS": "1"},
        ):
            project = Path(temporary) / "published-site"
            (project / "node_modules").mkdir(parents=True)
            (project / ".next").mkdir()
            (project / "intake").mkdir()
            marker = project / "intake" / "site-identity.json"
            marker.write_text("{}", encoding="utf-8")

            removed = _prune_success_build_artifacts({"publish": True}, "published-site")

            self.assertEqual(removed, ["node_modules", ".next"])
            self.assertTrue(marker.is_file())

    def test_completion_result_persists_online_acceptance_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"GAMEWIKI_PROJECTS_ROOT": temporary}):
            project = Path(temporary) / "verified-game"
            (project / ".gamewiki").mkdir(parents=True)
            (project / "content" / "en" / "guide").mkdir(parents=True)
            (project / "content" / "en" / "guide" / "one.mdx").write_text("# One", encoding="utf-8")
            (project / "intake").mkdir()
            (project / "intake" / "site-plan.json").write_text(json.dumps({
                "categories": [{"id": "guide", "status": "published"}],
            }), encoding="utf-8")
            (project / "intake" / "factory-release.json").write_text(
                json.dumps({"release": "v1_0722"}), encoding="utf-8",
            )
            (project / ".gamewiki" / "publish.json").write_text(json.dumps({
                "stages": {
                    "github": {"visibility": "PRIVATE", "repo": "owner/verified-game"},
                    "hosting": {"provider": "cloudflare-pages", "status": "manual_action_required"},
                    "onlineVerification": {"status": "complete", "origin": "https://verified.game"},
                },
            }), encoding="utf-8")
            result = _completion_result({"taskType": "site", "publish": True}, "verified-game")
        self.assertEqual(result["articles"]["english"], 1)
        self.assertEqual(result["factoryRelease"], "v1_0722")
        self.assertEqual(result["categories"], ["guide"])
        self.assertEqual(result["hosting"]["provider"], "cloudflare-pages")
        self.assertEqual(result["onlineVerification"]["status"], "complete")
        self.assertNotIn("token", json.dumps(result).casefold())

    def test_database_migrates_persisted_result_column(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"GAMEWIKI_DATA_DIR": temporary}):
            with connect() as db:
                columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)").fetchall()}
                notification_columns = {
                    row["name"] for row in db.execute("PRAGMA table_info(notifications)").fetchall()
                }
                tables = {
                    row["name"]
                    for row in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
            self.assertIn("result_json", columns)
            self.assertIn("quota_provider", columns)
            self.assertIn("delivered_at", notification_columns)
            self.assertIn("quota_circuits", tables)

    def test_terminal_event_creates_durable_acknowledgeable_notification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"GAMEWIKI_DATA_DIR": temporary}
        ):
            config_path = Path(temporary) / "game.json"
            config_path.write_text(
                json.dumps({"game": "Notify Game", "platform": "roblox"}),
                encoding="utf-8",
            )
            job_id = submit(config_path)
            with connect() as db:
                db.execute(
                    "UPDATE jobs SET status='needs_attention',current_stage='pipeline' WHERE id=?",
                    (job_id,),
                )
                _event(
                    db,
                    job_id,
                    "attempt.finished",
                    notify=True,
                    attempt=1,
                    status="needs_attention",
                    errorClass="needs_attention",
                )

            pending = pending_notifications()
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["job_id"], job_id)
            self.assertEqual(pending[0]["event_status"], "needs_attention")
            self.assertTrue(pending[0]["needsAttention"])
            self.assertNotIn("config_json", pending[0])
            self.assertEqual(
                acknowledge_notifications([pending[0]["notification_id"]]), 1
            )
            self.assertEqual(pending_notifications(), [])

    def test_job_logs_are_utf8_safe_on_legacy_windows_console(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"GAMEWIKI_DATA_DIR": temporary}):
            config_path = Path(temporary) / "game.json"
            config_path.write_text(json.dumps({"game": "Unicode Game", "platform": "roblox"}), encoding="utf-8")
            job_id = submit(config_path)
            log_path = Path(temporary) / "unicode.log"
            log_path.write_text("✅ translated\n", encoding="utf-8")
            with connect() as db:
                db.execute("UPDATE jobs SET log_path=? WHERE id=?", (str(log_path), job_id))
            env = os.environ.copy()
            env["GAMEWIKI_DATA_DIR"] = temporary
            env["PYTHONIOENCODING"] = "gbk"
            result = subprocess.run(
                [sys.executable, "gamewiki.py", "jobs", "logs", job_id, "--tail", "5"],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
            self.assertIn("✅ translated", result.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
