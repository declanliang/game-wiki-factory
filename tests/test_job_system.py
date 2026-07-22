from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_system import _completion_result, _execution_config, _prepare_full_build, _prune_success_build_artifacts, classify_failure, claim, connect, normalize_config, submit, submit_batch


class JobSystemTests(unittest.TestCase):
    def test_full_build_refreshes_only_first_attempt(self) -> None:
        config = normalize_config({"game": "Test Game", "platform": "roblox", "fullBuild": True})
        self.assertEqual(_execution_config(config, 1)["refresh"], {"basicInfo": True, "keywords": True, "articles": True})
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

    def test_rebuild_operation_automatically_replaces_existing_publication(self) -> None:
        config = normalize_config({"game": "Old Site", "operation": "rebuild", "publish": True})
        self.assertTrue(config["fullBuild"])
        self.assertTrue(config["publication"]["reuseExisting"])
        self.assertTrue(config["publication"]["replaceRepositoryContents"])

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
        self.assertEqual(classify_failure("Two Roblox candidates are too close to select safely"), "needs_attention")
        self.assertEqual(classify_failure("unknown build problem"), "needs_attention")

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

    def test_publication_contract_accepts_replace_existing(self) -> None:
        config = normalize_config({
            "game": "Old Site",
            "platform": "roblox",
            "publish": True,
            "fullBuild": True,
            "publication": {
                "githubRepo": "old-site",
                "reuseExisting": True,
                "replaceRepositoryContents": True,
                "vercelProject": "old-site",
            },
        })
        self.assertTrue(config["publication"]["replaceRepositoryContents"])

    def test_full_build_archives_existing_workspace_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"GAMEWIKI_PROJECTS_ROOT": temporary}):
            project = Path(temporary) / "old-site"
            project.mkdir()
            (project / "old.txt").write_text("old", encoding="utf-8")
            backup = _prepare_full_build({"fullBuild": True}, "old-site", 1)
            self.assertFalse(project.exists())
            self.assertTrue((backup / "old.txt").is_file())
            self.assertIsNone(_prepare_full_build({"fullBuild": True}, "old-site", 2))

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
            (project / ".gamewiki" / "publish.json").write_text(json.dumps({
                "stages": {
                    "github": {"visibility": "PRIVATE", "repo": "owner/verified-game"},
                    "vercel": {"status": "complete", "deploymentUrl": "https://verified-game.vercel.app"},
                    "onlineVerification": {"status": "complete", "origin": "https://verified.game"},
                },
            }), encoding="utf-8")
            result = _completion_result({"taskType": "site", "publish": True}, "verified-game")
        self.assertEqual(result["articles"]["english"], 1)
        self.assertEqual(result["categories"], ["guide"])
        self.assertEqual(result["onlineVerification"]["status"], "complete")
        self.assertNotIn("token", json.dumps(result).casefold())

    def test_database_migrates_persisted_result_column(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"GAMEWIKI_DATA_DIR": temporary}):
            with connect() as db:
                columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)").fetchall()}
            self.assertIn("result_json", columns)

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
