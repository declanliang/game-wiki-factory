from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import orchestrate_wiki as orchestrator


class OrchestratorTests(unittest.TestCase):
    def test_replace_directory_is_noop_when_source_is_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / "articles"
            checkpoint.mkdir()
            marker = checkpoint / "kept.mdx"
            marker.write_text("checkpoint", encoding="utf-8")

            orchestrator.replace_directory(checkpoint, checkpoint)

            self.assertEqual(marker.read_text(encoding="utf-8"), "checkpoint")

    def test_factory_defaults_use_bundled_modules_and_sibling_output(self) -> None:
        args = orchestrator.build_parser().parse_args(["Test Game"])
        self.assertEqual(args.template_dir, orchestrator.ROOT / "template")
        self.assertEqual(
            args.seo_scout_dir,
            orchestrator.ROOT / "pipeline" / "seo-scout",
        )
        self.assertEqual(args.output_root, orchestrator.ROOT.parent)

    def test_projects_dir_remains_a_compatibility_alias(self) -> None:
        args = orchestrator.build_parser().parse_args(
            ["Test Game", "--projects-dir", "D:/sites"]
        )
        self.assertEqual(args.output_root, Path("D:/sites"))

    def test_recluster_flag_is_available_for_raw_source_reuse(self) -> None:
        args = orchestrator.build_parser().parse_args(["Hellhole", "--recluster-keywords"])
        self.assertTrue(args.recluster_keywords)

    def test_run_command_writes_stage_and_complete_run_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage_log = root / "logs" / "stage.log"
            run_log = root / "logs" / "run.log"

            orchestrator.run_command(
                [sys.executable, "-c", "print('logged child output')"],
                cwd=root,
                env=dict(os.environ),
                log_path=stage_log,
                run_log_path=run_log,
            )

            stage_text = stage_log.read_text(encoding="utf-8")
            run_text = run_log.read_text(encoding="utf-8")
        for text in (stage_text, run_text):
            self.assertIn("logged child output", text)
            self.assertIn("[exit] 0", text)
            self.assertIn("[cwd]", text)

    def test_slug_and_seo_project_names_match_existing_tools(self) -> None:
        self.assertEqual(orchestrator.slugify("ANIME PARADOX X"), "anime-paradox-x")
        self.assertEqual(orchestrator.seo_project_name("Anime Paradox X"), "anime_paradox_x")
        self.assertEqual(orchestrator.keyword_topic("Hellhole"), "Hellhole Roblox")
        self.assertEqual(orchestrator.keyword_topic("Hellhole Roblox"), "Hellhole Roblox")

    def test_dotenv_aliases_are_mapped_without_replacing_process_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".env").write_text(
                "toapis_API_KEY=basic-secret\n"
                "dataforseo_name=legacy-login\n"
                "dataforseo_password=legacy-password\n",
                encoding="utf-8",
            )
            env = orchestrator.build_subprocess_env(
                root,
                base_env={"TOAPIS_API_KEY": "process-secret"},
            )

        self.assertEqual(env["TOAPIS_API_KEY"], "process-secret")
        self.assertEqual(env["TOAPIS_KEY"], "process-secret")
        self.assertEqual(env["LLM_API_KEY"], "process-secret")
        self.assertEqual(env["DATAFORSEO_LOGIN"], "legacy-login")
        self.assertEqual(env["DATAFORSEO_PASSWORD"], "legacy-password")
        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(env["PYTHONUTF8"], "1")

    def test_keyword_bridge_uses_canonical_name_and_non_english_languages(self) -> None:
        raw = {
            "topic_name": "anime paradox x",
            "categories": [
                {"category": "guide", "keywords": ["anime paradox x guide"]},
                {"category": "tier list", "keywords": ["anime paradox x tier list"]},
                {"category": "units", "keywords": ["anime paradox x units"]},
                {"category": "traits", "keywords": ["anime paradox x traits"]},
            ],
        }
        identity = {"GAME_NAME": "Anime Paradox X", "LANGUAGES": ["en", "es"]}

        bridged = orchestrator.bridge_keywords(raw, identity)

        self.assertEqual(bridged["game_name"], "Anime Paradox X")
        self.assertEqual(bridged["filter_keyword"], "Roblox Anime Paradox X")
        self.assertEqual(bridged["languages"], ["es"])
        self.assertEqual(bridged["categories"], raw["categories"])

    def test_keyword_bridge_accepts_one_evidence_backed_category(self) -> None:
        raw = {
            "categories": [
                {"category": "guide", "keywords": ["hellhole roblox guide"]},
                {"category": "bosses", "keywords": ["hellhole roblox boss"]},
                {"category": "floors", "keywords": ["hellhole roblox floor"]},
            ]
        }
        identity = {"GAME_NAME": "Hellhole", "LANGUAGES": ["en", "es"]}
        bridged = orchestrator.bridge_keywords(raw, identity)
        self.assertEqual(len(bridged["categories"]), 3)

    def test_trusted_keyword_context_contains_official_identity_and_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            intake = Path(temporary)
            (intake / "site-content.json").write_text(
                json.dumps({"site": {"description": "Officially verified upgrades"}}),
                encoding="utf-8",
            )
            context = orchestrator.build_trusted_keyword_context(
                intake,
                {
                    "GAME_NAME": "Hellhole",
                    "OFFICIAL_GAME_URL": "https://www.roblox.com/games/1/hellhole",
                },
            )
        self.assertEqual(context["identity"]["game_name"], "Hellhole")
        self.assertIn("upgrades", context["site_content"]["site"]["description"])

    def test_latest_keyword_run_accepts_raw_only_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "output" / "hellhole-20260719T015036Z"
            raw = run / "raw"
            raw.mkdir(parents=True)
            for name in ("labs.json", "trends.json", "autocomplete.json", "youtube.json"):
                (raw / name).write_text("{}", encoding="utf-8")
            self.assertEqual(orchestrator.latest_keyword_run([root], "hellhole"), run)

    def test_article_validation_requires_identical_locale_trees(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for locale in ("en", "es"):
                path = root / locale / "guide" / "starter.mdx"
                path.parent.mkdir(parents=True)
                path.write_text("export const metadata = {}\n", encoding="utf-8")

            counts = orchestrator.validate_articles(root, ["en", "es"])
            self.assertEqual(counts, {"en": 1, "es": 1})

            (root / "es" / "guide" / "starter.mdx").unlink()
            with self.assertRaises(orchestrator.PipelineError):
                orchestrator.validate_articles(root, ["en", "es"])

    def test_basic_output_contract_accepts_complete_template_intake(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            intake = output / "template-intake"
            favicon = intake / "favicon"
            favicon.mkdir(parents=True)
            languages = ["en", "es", "de", "fr", "ja", "ko"]
            identity = {"GAME_NAME": "Test Game", "LANGUAGES": languages}
            (intake / "site-identity.json").write_text(json.dumps(identity), encoding="utf-8")
            (intake / "site-content.json").write_text("{}", encoding="utf-8")
            for locale in languages[1:]:
                (intake / f"site-content.{locale}.json").write_text("{}", encoding="utf-8")
            (intake / "hero.png").write_bytes(b"png")
            for name in orchestrator.FAVICON_FILES:
                (favicon / name).write_bytes(b"x")
            (output / "template-validation-report.json").write_text(
                json.dumps({"status": "pass"}), encoding="utf-8"
            )
            # The real tool also writes convenience copies at the output root;
            # the orchestrator must still prefer the strictly validated package.
            (output / "site-identity.json").write_text(json.dumps(identity), encoding="utf-8")
            (output / "site-content.json").write_text("{}", encoding="utf-8")

            actual_intake, actual_identity, languages = orchestrator.validate_basic_output(output)

        self.assertEqual(actual_intake, intake)
        self.assertEqual(actual_identity, identity)
        self.assertEqual(languages, ["en", "es", "de", "fr", "ja", "ko"])


if __name__ == "__main__":
    unittest.main()
