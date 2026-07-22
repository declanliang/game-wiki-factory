from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from publisher import _deploy_with_vercel_cli, _ensure_private_github_repo, _replace_remote_main, _resolve_git_author, _set_vercel_site_url, _validate_project, _vercel_project_payload


class PublisherValidationTests(unittest.TestCase):
    def _project(self, root: Path) -> Path:
        (root / ".gamewiki").mkdir()
        (root / "intake").mkdir()
        (root / ".gamewiki" / "manifest.json").write_text(json.dumps({"status": "complete"}), encoding="utf-8")
        (root / "package.json").write_text("{}", encoding="utf-8")
        for name in ("site-identity.json", "site-content.json", "site-plan.json"):
            (root / "intake" / name).write_text("{}", encoding="utf-8")
        return root

    def test_complete_project_is_publishable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = _validate_project(self._project(Path(temporary)))
        self.assertEqual(manifest["status"], "complete")

    def test_secret_file_blocks_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self._project(Path(temporary))
            (project / ".env.production").write_text("TOKEN=secret", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Secret-like"):
                _validate_project(project)

    @patch("publisher._run")
    def test_existing_public_repository_is_made_private_and_rechecked(self, run) -> None:
        run.side_effect = ["PUBLIC", "", "PRIVATE"]

        _ensure_private_github_repo("owner/game", Path("C:/game"), {"GH_TOKEN": "hidden"})

        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn("--visibility", commands[1])
        self.assertIn("private", commands[1])
        self.assertEqual(commands[0], commands[2])

    @patch("publisher._run", return_value="PUBLIC")
    def test_private_visibility_is_a_required_postcondition(self, _run) -> None:
        with self.assertRaisesRegex(RuntimeError, "must be PRIVATE"):
            _ensure_private_github_repo("owner/game", Path("C:/game"), {})

    def test_vercel_project_creation_never_sets_environment_variables(self) -> None:
        payload = _vercel_project_payload("game", "owner/game")
        self.assertNotIn("environmentVariables", payload)
        self.assertEqual(payload["gitRepository"]["repo"], "owner/game")

    @patch("publisher.subprocess.run")
    @patch("publisher._run")
    def test_replace_remote_main_backs_up_then_uses_force_with_lease(self, run, subprocess_run) -> None:
        run.side_effect = lambda command, *_args, **_kwargs: "abc123" if command[:3] == ["git", "rev-parse", "refs/remotes/origin/main"] else ""
        tag = _replace_remote_main(
            Path("C:/game"),
            "owner/game",
            {},
            ("declanliang", "130889021+declanliang@users.noreply.github.com"),
        )
        commands = [call.args[0] for call in run.call_args_list]
        self.assertTrue(tag.startswith("pre-rebuild-"))
        self.assertTrue(any(command[:3] == ["git", "push", "origin"] and "refs/tags/" in command[3] for command in commands))
        self.assertTrue(any(command[:2] == ["git", "push"] and "--force-with-lease=main:abc123" in command for command in commands))
        commit = next(command for command in commands if "commit" in command)
        self.assertIn("user.name=declanliang", commit)
        self.assertIn("user.email=130889021+declanliang@users.noreply.github.com", commit)

    @patch("publisher._run", return_value="declanliang\t130889021")
    def test_git_author_uses_authenticated_github_noreply_identity(self, run) -> None:
        author = _resolve_git_author(Path("C:/game"), {"GH_TOKEN": "hidden"})
        self.assertEqual(author, ("declanliang", "130889021+declanliang@users.noreply.github.com"))
        self.assertNotIn("hidden", run.call_args.args[0])

    @patch("publisher.shutil.which", return_value="vercel")
    @patch("publisher._run")
    def test_explicit_site_url_sets_production(self, run, _which) -> None:
        origin = _set_vercel_site_url(Path("C:/game"), "game", "game.example/path")
        self.assertEqual(origin, "https://game.example")
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0][:4], ["vercel", "link", "--yes", "--project"])
        self.assertEqual(commands[1][4], "production")

    @patch("publisher.shutil.which", return_value="vercel")
    @patch("publisher._run", side_effect=["", "https://game.vercel.app"])
    def test_deploy_links_existing_vercel_project_before_production(self, run, _which) -> None:
        url = _deploy_with_vercel_cli(Path("C:/game"), "existing-project", {"VERCEL_TOKEN": "hidden"})
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0][:5], ["vercel", "link", "--yes", "--project", "existing-project"])
        self.assertIn("--prod", commands[1])
        self.assertNotIn("hidden", commands[0])
        self.assertNotIn("hidden", commands[1])
        self.assertNotIn("--token", commands[0])
        self.assertNotIn("--token", commands[1])
        self.assertEqual(url, "https://game.vercel.app")


if __name__ == "__main__":
    unittest.main()
