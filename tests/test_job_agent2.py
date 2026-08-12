import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_agent2 import _codex_child_env, _codex_command, _ensure_schema, _extract_last_json_object, recover_once
from job_system import _event, connect, submit
from orchestrate_wiki import write_json


class JobAgent2Tests(unittest.TestCase):
    def _job(self, temporary: str, error: str, stage: str = "articles") -> tuple[str, Path]:
        config = Path(temporary) / "job.json"
        config.write_text(json.dumps({"game": "Repair Game", "platform": "roblox"}), encoding="utf-8")
        job_id = submit(config)
        project = Path(temporary) / "projects" / "repair-game"
        state = project / ".gamewiki"
        state.mkdir(parents=True)
        write_json(state / "manifest.json", {"status": "failed", "stages": {stage: {"status": "failed"}}})
        with connect() as db:
            db.execute(
                """UPDATE jobs SET status='needs_attention',current_stage=?,last_error=?,
                          finished_at='2020-01-01T00:00:00+00:00' WHERE id=?""",
                (stage, error, job_id),
            )
            _event(db, job_id, "attempt.finished", notify=True, status="needs_attention")
        return job_id, project

    def test_dry_run_lists_eligible_job_without_mutating_status(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "GAMEWIKI_DATA_DIR": str(Path(temporary) / "data"),
                "GAMEWIKI_PROJECTS_ROOT": str(Path(temporary) / "projects"),
            },
        ):
            job_id, _project = self._job(temporary, "TranslationError: duplicate title in es article")
            result = recover_once(dry_run=True)
            with connect() as db:
                status = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
        self.assertEqual([item["jobId"] for item in result], [job_id])
        self.assertEqual(status, "needs_attention")

    def test_dry_run_lists_article_generation_failures(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "GAMEWIKI_DATA_DIR": str(Path(temporary) / "data"),
                "GAMEWIKI_PROJECTS_ROOT": str(Path(temporary) / "projects"),
            },
        ):
            job_id, _project = self._job(
                temporary,
                "Article generation failed for 5 item(s); no incomplete response was accepted. Re-run without --overwrite to retry only the missing articles.",
            )
            result = recover_once(dry_run=True)
        self.assertEqual([item["jobId"] for item in result], [job_id])

    def test_stale_agent2_run_does_not_consume_retry_budget(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "GAMEWIKI_DATA_DIR": str(Path(temporary) / "data"),
                "GAMEWIKI_PROJECTS_ROOT": str(Path(temporary) / "projects"),
                "GAMEWIKI_AGENT2_MAX_RUNS": "1",
            },
        ):
            job_id, _project = self._job(temporary, "ToAPIs returned HTTP 524", stage="pipeline")
            with connect() as db:
                _ensure_schema(db)
                db.execute(
                    """INSERT INTO agent2_runs(job_id,number,original_status,status,started_at)
                       VALUES(?,?,?,?,?)""",
                    (job_id, 1, "failed", "stale", "2020-01-01T00:00:00+00:00"),
                )
            result = recover_once(dry_run=True)
        self.assertEqual([item["jobId"] for item in result], [job_id])

    def test_skips_quota_and_permission_failures(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "GAMEWIKI_DATA_DIR": str(Path(temporary) / "data"),
                "GAMEWIKI_PROJECTS_ROOT": str(Path(temporary) / "projects"),
            },
        ):
            self._job(temporary, "Cloudflare permission forbidden")
            self.assertEqual(recover_once(dry_run=True), [])

    def test_codex_env_accepts_factory_lowercase_auth_fields(self):
        with patch.dict(
            os.environ,
            {
                "GAMEWIKI_AGENT2_OPENAI_API_KEY": "test-key",
                "GAMEWIKI_AGENT2_OPENAI_BASE_URL": "https://api.example.test/v1",
                "GAMEWIKI_AGENT2_CODEX_MODEL": "gpt-test",
                "base_url": "https://api.example.test/v1",
                "model": "gpt-test",
                "model_reasoning_effort": "medium",
                "disable_response_storage": "true",
                "CLOUDFLARE_API_TOKEN": "cloudflare-secret",
                "FACTORY_GITHUB_TOKEN": "github-secret",
                "TOAPIS_API_KEY": "toapis-secret",
                "LLM_API_KEY_1": "llm-secret",
                "GAMEWIKI_CONTROL_TOKEN": "control-secret",
            },
            clear=True,
        ):
            env = _codex_child_env()
            command = _codex_command(Path("project"), Path("report.json"), env)
        self.assertEqual(env["CODEX_API_KEY"], "test-key")
        self.assertEqual(env["OPENAI_API_KEY"], "test-key")
        self.assertEqual(env["OPENAI_BASE_URL"], "https://api.example.test/v1")
        self.assertIn('model_provider="agent2_proxy"', command)
        self.assertIn('model_providers.agent2_proxy.base_url="https://api.example.test/v1"', command)
        self.assertIn('model_providers.agent2_proxy.env_key="CODEX_API_KEY"', command)
        self.assertIn("--model", command)
        self.assertIn("gpt-test", command)
        self.assertIn("model_reasoning_effort=\"medium\"", command)
        self.assertIn("disable_response_storage=true", command)
        self.assertNotIn("CLOUDFLARE_API_TOKEN", env)
        self.assertNotIn("FACTORY_GITHUB_TOKEN", env)
        self.assertNotIn("TOAPIS_API_KEY", env)
        self.assertNotIn("LLM_API_KEY_1", env)
        self.assertNotIn("GAMEWIKI_CONTROL_TOKEN", env)

    def test_repaired_report_requeues_for_worker(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "GAMEWIKI_DATA_DIR": str(Path(temporary) / "data"),
                "GAMEWIKI_PROJECTS_ROOT": str(Path(temporary) / "projects"),
                "GAMEWIKI_AGENT2_CODEX_BIN": sys.executable,
                "GAMEWIKI_AGENT2_CODEX_COMMAND_JSON": json.dumps([
                    sys.executable,
                    "-c",
                    "import json,sys; json.dump({'status':'repaired','summary':'fixed mdx','filesChanged':['content/en/a.mdx'],'verification':['local check passed']}, open(sys.argv[1], 'w', encoding='utf-8'))",
                    "{report}",
                ]),
            },
        ):
            job_id, _project = self._job(temporary, "article preflight failed: duplicate description")
            result = recover_once(limit=1)
            with connect() as db:
                status = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
                event_count = db.execute(
                    "SELECT COUNT(*) FROM events WHERE job_id=? AND event='job.agent2_requeued'",
                    (job_id,),
                ).fetchone()[0]
        self.assertEqual(result[0]["status"], "succeeded")
        self.assertEqual(status, "retry_wait")
        self.assertEqual(event_count, 1)

    def test_extract_last_json_object_salvages_inline_report(self):
        text = "noise before\n{\"status\":\"repaired\",\"summary\":\"fixed\"}\nnoise after"
        self.assertEqual(_extract_last_json_object(text), "{\"status\":\"repaired\",\"summary\":\"fixed\"}")

    def test_repaired_stdout_report_is_accepted_when_report_file_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "GAMEWIKI_DATA_DIR": str(Path(temporary) / "data"),
                "GAMEWIKI_PROJECTS_ROOT": str(Path(temporary) / "projects"),
                "GAMEWIKI_AGENT2_CODEX_BIN": sys.executable,
                "GAMEWIKI_AGENT2_CODEX_COMMAND_JSON": json.dumps([
                    sys.executable,
                    "-c",
                    (
                        "import json,sys; "
                        "print('prefix'); "
                        "print(json.dumps({'status':'repaired','summary':'fixed mdx','filesChanged':['content/en/a.mdx'],'verification':['local check passed']}));"
                    ),
                ]),
            },
        ):
            job_id, _project = self._job(temporary, "article preflight failed: duplicate description")
            result = recover_once(limit=1)
            with connect() as db:
                status = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
                event_count = db.execute(
                    "SELECT COUNT(*) FROM events WHERE job_id=? AND event='job.agent2_requeued'",
                    (job_id,),
                ).fetchone()[0]
        self.assertEqual(result[0]["status"], "succeeded")
        self.assertEqual(status, "retry_wait")
        self.assertEqual(event_count, 1)


if __name__ == "__main__":
    unittest.main()
