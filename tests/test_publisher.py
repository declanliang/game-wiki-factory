from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from publisher import (
    _cloudflare_create_git_deployment,
    _cloudflare_credentials,
    _cloudflare_git_project_payload,
    _deploy_cloudflare_pages,
    _ensure_cloudflare_project,
    _ensure_private_github_repo,
    _resolve_cloudflare_project,
    _resolve_git_author,
    _set_cloudflare_site_url,
    _validate_cloudflare_git_project,
    _validate_project,
    _verify_online_deployment,
    _wait_cloudflare_deployment,
    _wait_cloudflare_commit_deployment,
)


class PublisherValidationTests(unittest.TestCase):
    def test_cloudflare_credentials_accept_preferred_and_legacy_names(self) -> None:
        self.assertEqual(
            _cloudflare_credentials({
                "CLOUDFLARE_ACCOUNT_ID": "account",
                "CLOUDFLARE_API_TOKEN": "token",
            }),
            ("account", "token"),
        )
        self.assertEqual(
            _cloudflare_credentials({
                "cf_accountid": "legacy-account",
                "cf_pages_api_key": "legacy-token",
            }),
            ("legacy-account", "legacy-token"),
        )
        with self.assertRaisesRegex(RuntimeError, "requires CLOUDFLARE_ACCOUNT_ID"):
            _cloudflare_credentials({})

    def _git_project(self, **overrides) -> dict:
        project = {
            "id": "project-id",
            "name": "game",
            "subdomain": "game.pages.dev",
            "source": {
                "type": "github",
                "config": {
                    "owner": "owner",
                    "repo_name": "game",
                    "production_branch": "main",
                },
            },
            "build_config": {
                "build_command": "npm run build",
                "destination_dir": "out",
                "root_dir": "",
            },
            "deployment_configs": {
                "production": {
                    "env_vars": {},
                },
            },
        }
        project.update(overrides)
        return project

    def test_cloudflare_git_project_payload_is_buildable_and_main_only(self) -> None:
        payload = _cloudflare_git_project_payload("game", "owner/game")
        self.assertEqual(payload["source"]["type"], "github")
        self.assertEqual(payload["source"]["config"]["owner"], "owner")
        self.assertEqual(payload["source"]["config"]["repo_name"], "game")
        self.assertTrue(payload["source"]["config"]["production_deployments_enabled"])
        self.assertEqual(payload["source"]["config"]["preview_deployment_setting"], "none")
        self.assertEqual(payload["build_config"], {
            "build_command": "npm run build",
            "destination_dir": "out",
            "root_dir": "",
        })

    @patch("publisher.urllib.request.urlopen")
    def test_cloudflare_git_deployment_uses_multipart_branch(self, urlopen) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "success": True,
            "result": {"id": "deployment-id"},
        }).encode("utf-8")
        urlopen.return_value = response

        deployment = _cloudflare_create_git_deployment(
            "account",
            "hidden-token",
            "game",
        )

        self.assertEqual(deployment["id"], "deployment-id")
        request = urlopen.call_args.args[0]
        self.assertIn("multipart/form-data", request.headers["Content-type"])
        self.assertIn(b'name="branch"', request.data)
        self.assertIn(b"main", request.data)
        self.assertNotIn("hidden-token", request.full_url)
        self.assertNotIn(b"hidden-token", request.data)

    @patch("publisher._cloudflare_request")
    def test_cloudflare_project_creation_is_git_integrated(self, request) -> None:
        request.side_effect = [
            RuntimeError("HTTP 404 from project"),
            self._git_project(),
        ]
        project, created = _ensure_cloudflare_project(
            "account", "token", "game", "owner/game"
        )
        self.assertEqual(project["id"], "project-id")
        self.assertTrue(created)
        self.assertEqual(request.call_args_list[1].args[0], "POST")
        payload = request.call_args_list[1].args[4]
        self.assertEqual(payload["source"]["config"]["repo_name"], "game")
        self.assertEqual(payload["build_config"]["destination_dir"], "out")

    def test_direct_upload_project_is_never_reused_or_converted(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Direct Upload"):
            _validate_cloudflare_git_project(
                {"name": "game", "source": None},
                "owner/game",
            )

    def test_git_project_must_match_repository_and_build_contract(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "different Git source"):
            _validate_cloudflare_git_project(
                self._git_project(source={
                    "type": "github",
                    "config": {
                        "owner": "other",
                        "repo_name": "game",
                        "production_branch": "main",
                    },
                }),
                "owner/game",
            )
        with self.assertRaisesRegex(RuntimeError, "incompatible build"):
            _validate_cloudflare_git_project(
                self._git_project(build_config={
                    "build_command": "",
                    "destination_dir": "",
                    "root_dir": "",
                }),
                "owner/game",
            )

    @patch("publisher._ensure_cloudflare_project")
    def test_git_authorization_failure_has_operator_action(self, ensure_project) -> None:
        ensure_project.side_effect = RuntimeError(
            "HTTP 400: GitHub installation is not authorized for repository"
        )
        with self.assertRaisesRegex(RuntimeError, "GitHub App access"):
            _resolve_cloudflare_project(
                "account",
                "token",
                "game",
                "owner/game",
            )

    @patch("publisher._cloudflare_request")
    def test_cloudflare_site_url_patch_is_scoped_to_production(self, request) -> None:
        changed = _set_cloudflare_site_url(
            "account",
            "token",
            "game",
            "https://game.example",
            self._git_project(),
            created=True,
        )
        self.assertTrue(changed)
        payload = request.call_args.args[4]
        self.assertEqual(
            payload["deployment_configs"]["production"]["env_vars"]["NEXT_PUBLIC_SITE_URL"],
            {"type": "plain_text", "value": "https://game.example"},
        )
        self.assertNotIn("token", json.dumps(payload).casefold())

    @patch("publisher._cloudflare_request")
    def test_cloudflare_site_url_does_not_rewrite_matching_environment(self, request) -> None:
        project = self._git_project(deployment_configs={
            "production": {
                "env_vars": {
                    "NEXT_PUBLIC_SITE_URL": {
                        "type": "plain_text",
                        "value": "https://game.example",
                    },
                    "AD_NATIVE_BANNER_B64": {"type": "secret_text", "value": ""},
                },
            },
        })
        changed = _set_cloudflare_site_url(
            "account",
            "token",
            "game",
            "https://game.example",
            project,
            created=False,
        )
        self.assertFalse(changed)
        request.assert_not_called()

    @patch("publisher._cloudflare_request")
    def test_cloudflare_site_url_refuses_to_overwrite_unrelated_environment(self, request) -> None:
        project = self._git_project(deployment_configs={
            "production": {
                "env_vars": {
                    "AD_NATIVE_BANNER_B64": {"type": "secret_text", "value": ""},
                },
            },
        })
        with self.assertRaisesRegex(RuntimeError, "Refusing to replace"):
            _set_cloudflare_site_url(
                "account",
                "token",
                "game",
                "https://game.example",
                project,
                created=False,
            )
        request.assert_not_called()

    @patch("publisher._wait_cloudflare_deployment")
    @patch("publisher._cloudflare_create_git_deployment")
    @patch("publisher._set_cloudflare_site_url")
    @patch("publisher._resolve_cloudflare_project")
    def test_cloudflare_deploy_uses_git_integration(
        self, resolve_project, set_site_url, create_deployment, wait_deployment
    ) -> None:
        resolve_project.return_value = ("game", self._git_project(), True)
        set_site_url.return_value = True
        create_deployment.return_value = {"id": "deployment-id"}
        wait_deployment.return_value = {
            "id": "deployment-id",
            "url": "https://deploy.game.pages.dev",
            "deployment_trigger": {"metadata": {"commit_hash": "abc123"}},
            "latest_stage": {"status": "success"},
        }
        result = _deploy_cloudflare_pages(
            Path("C:/game"),
            "game",
            "owner/game",
            "game.example/path",
            "abc123",
            {"cf_accountid": "account", "cf_pages_api_key": "hidden-token"},
        )
        self.assertEqual(result["status"], "deployed")
        self.assertEqual(result["deploymentMode"], "git-integration")
        self.assertEqual(result["source"]["repo"], "owner/game")
        create_deployment.assert_called_once_with(
            "account", "hidden-token", "game", "main"
        )
        set_site_url.assert_called_once_with(
            "account",
            "hidden-token",
            "game",
            "https://game.example",
            resolve_project.return_value[1],
            created=True,
        )
        wait_deployment.assert_called_once()

    @patch("publisher.time.sleep")
    @patch("publisher._cloudflare_request")
    def test_cloudflare_wait_polls_exact_deployment_and_commit(self, request, _sleep) -> None:
        request.side_effect = [
            {
                "id": "deployment-id",
                "latest_stage": {"name": "build", "status": "active"},
                "deployment_trigger": {"metadata": {"commit_hash": "abc123"}},
            },
            {
                "id": "deployment-id",
                "latest_stage": {"name": "deploy", "status": "success"},
                "deployment_trigger": {"metadata": {"commit_hash": "abc123"}},
            },
        ]
        result = _wait_cloudflare_deployment(
            "account",
            "token",
            "game",
            "deployment-id",
            "abc123",
            attempts=2,
        )
        self.assertEqual(result["id"], "deployment-id")
        self.assertTrue(all(
            call.args[3].endswith("/deployments/deployment-id")
            for call in request.call_args_list
        ))

    @patch("publisher._cloudflare_request")
    def test_cloudflare_wait_rejects_stale_commit(self, request) -> None:
        request.return_value = {
            "id": "deployment-id",
            "latest_stage": {"name": "deploy", "status": "success"},
            "deployment_trigger": {"metadata": {"commit_hash": "other"}},
        }
        with self.assertRaisesRegex(RuntimeError, "expected abc123"):
            _wait_cloudflare_deployment(
                "account",
                "token",
                "game",
                "deployment-id",
                "abc123",
                attempts=1,
            )

    @patch("publisher._wait_cloudflare_deployment")
    @patch("publisher._cloudflare_request")
    def test_git_integration_deployment_is_discovered_by_commit(
        self, request, wait_deployment
    ) -> None:
        request.return_value = [
            {
                "id": "deployment-id",
                "environment": "production",
                "deployment_trigger": {"metadata": {"commit_hash": "abc123"}},
            }
        ]
        wait_deployment.return_value = {"id": "deployment-id"}
        result = _wait_cloudflare_commit_deployment(
            "account", "token", "game", "abc123", discovery_attempts=1
        )
        self.assertEqual(result["id"], "deployment-id")
        wait_deployment.assert_called_once_with(
            "account",
            "token",
            "game",
            "deployment-id",
            "abc123",
            log_path=None,
        )

    def _project(self, root: Path) -> Path:
        (root / ".gamewiki").mkdir()
        (root / "intake").mkdir()
        (root / ".gamewiki" / "manifest.json").write_text(json.dumps({"status": "complete"}), encoding="utf-8")
        (root / "package.json").write_text("{}", encoding="utf-8")
        for name in (
            "site-identity.json",
            "site-content.json",
            "site-plan.json",
            "publication-plan.json",
            "site-theme.json",
        ):
            (root / "intake" / name).write_text("{}", encoding="utf-8")
        (root / "intake" / "factory-release.json").write_text(
            json.dumps({"release": "v1_0728"}), encoding="utf-8"
        )
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

    def test_unstamped_legacy_project_cannot_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self._project(Path(temporary))
            (project / "intake" / "factory-release.json").unlink()
            with self.assertRaisesRegex(RuntimeError, "factory-release"):
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

    @patch("publisher._run", return_value="declanliang\t130889021")
    def test_git_author_uses_authenticated_github_noreply_identity(self, run) -> None:
        author = _resolve_git_author(Path("C:/game"), {"GH_TOKEN": "hidden"})
        self.assertEqual(author, ("declanliang", "130889021+declanliang@users.noreply.github.com"))
        self.assertNotIn("hidden", run.call_args.args[0])

    @patch("publisher.shutil.which", return_value="npm")
    @patch("publisher.subprocess.run")
    def test_online_verification_is_a_logged_publish_postcondition(self, run, _which) -> None:
        run.return_value.returncode = 0
        run.return_value.stdout = "0 error(s).\n"
        run.return_value.stderr = ""
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            result = _verify_online_deployment(project, "https://game.example/", {"TOKEN": "hidden"})
            log = (project / ".gamewiki" / "deploy-verification.log").read_text(encoding="utf-8")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["origin"], "https://game.example")
        self.assertIn("0 error(s).", log)
        command = run.call_args.args[0]
        self.assertEqual(command, ["npm", "run", "verify:deploy"])
        self.assertEqual(run.call_args.kwargs["env"]["NEXT_PUBLIC_SITE_URL"], "https://game.example")
        self.assertNotIn("hidden", command)

    @patch("publisher.shutil.which", return_value="npm")
    @patch("publisher.subprocess.run")
    def test_online_verification_failure_blocks_publish(self, run, _which) -> None:
        run.return_value.returncode = 1
        run.return_value.stdout = "online sitemap target returned 404"
        run.return_value.stderr = ""
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, "online deployment verification failed"):
                _verify_online_deployment(project, "https://game.example", {})
            self.assertTrue((project / ".gamewiki" / "deploy-verification.log").is_file())


if __name__ == "__main__":
    unittest.main()
