from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from publisher import (
    _cloudflare_create_git_deployment,
    _cloudflare_credentials,
    _cloudflare_environment_payload,
    _cloudflare_git_project_payload,
    _deploy_cloudflare_pages,
    _deploy_cloudflare_workers_static_assets,
    _ensure_cloudflare_project,
    _ensure_workers_static_assets_runtime,
    _ensure_origin_remote,
    _ensure_private_github_repo,
    _github_repo_from_remote_url,
    _resolve_cloudflare_project,
    _resolve_git_author,
    _set_cloudflare_project_environment,
    _ensure_cloudflare_custom_domain,
    _ensure_cloudflare_dns_cname,
    _validate_cloudflare_git_project,
    _validate_project,
    _verify_online_deployment,
    _verify_online_advertising,
    _wait_cloudflare_deployment,
    _wait_cloudflare_commit_deployment,
    _workers_static_assets_config,
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
                "preview": {
                    "env_vars": {},
                },
                "production": {
                    "env_vars": {},
                },
            },
        }
        project.update(overrides)
        return project

    def test_cloudflare_git_project_payload_uses_production_deployment_for_acceptance(self) -> None:
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
    def test_cloudflare_environment_patch_sets_ads_and_preserves_unrelated_variables(self, request) -> None:
        ads = {name: f"encoded-{index}" for index, name in enumerate((
            "AD_NATIVE_BANNER_B64",
            "AD_NATIVE_BANNER_MOBILE_B64",
            "AD_BANNER_728X90_B64",
            "AD_BANNER_300X250_B64",
            "AD_BANNER_468X60_B64",
            "AD_SIDEBAR_160X600_B64",
            "AD_SIDEBAR_160X300_B64",
            "AD_MOBILE_320X50_B64",
        ))}
        project = self._git_project(deployment_configs={
            "preview": {
                "env_vars": {
                    "EXISTING_PREVIEW_SECRET": {"type": "secret_text", "value": ""},
                },
            },
            "production": {
                "env_vars": {
                    "EXISTING_ANALYTICS_ID": {
                        "type": "plain_text",
                        "value": "analytics-id",
                    },
                },
            },
        })

        def cloudflare_request(method, _account, _token, _path, payload=None):
            if method == "PATCH":
                for environment, config in payload["deployment_configs"].items():
                    project["deployment_configs"][environment]["env_vars"].update(
                        config["env_vars"]
                    )
                return project
            if method == "GET":
                return project
            self.fail(f"unexpected Cloudflare method {method}")

        request.side_effect = cloudflare_request
        configured = _set_cloudflare_project_environment(
            "account",
            "token",
            "game",
            "https://game.example",
            ads,
            project,
        )
        payload = request.call_args_list[0].args[4]
        preview = payload["deployment_configs"]["preview"]["env_vars"]
        production = payload["deployment_configs"]["production"]["env_vars"]
        self.assertEqual(set(preview), set(ads))
        self.assertTrue(all(value["type"] == "plain_text" for value in preview.values()))
        self.assertEqual(set(production), {"NEXT_PUBLIC_SITE_URL", *ads})
        self.assertEqual(
            production["NEXT_PUBLIC_SITE_URL"],
            {"type": "plain_text", "value": "https://game.example"},
        )
        self.assertEqual(configured, ("NEXT_PUBLIC_SITE_URL", *ads))
        self.assertNotIn("token", json.dumps(payload).casefold())
        self.assertIn(
            "EXISTING_PREVIEW_SECRET",
            project["deployment_configs"]["preview"]["env_vars"],
        )
        self.assertIn(
            "EXISTING_ANALYTICS_ID",
            project["deployment_configs"]["production"]["env_vars"],
        )
        self.assertEqual([call.args[0] for call in request.call_args_list], ["PATCH", "GET"])

    def test_cloudflare_environment_payload_requires_all_eight_ads(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "complete ordered 8-variable"):
            _cloudflare_environment_payload("https://game.example", {})

    @patch("publisher._http_response")
    def test_online_advertising_verifies_exact_eight_first_party_endpoints(self, response) -> None:
        formats = [
            "nativeBanner", "nativeBannerMobile", "banner728x90", "banner300x250",
            "banner468x60", "sidebar160x600", "sidebar160x300", "mobile320x50",
        ]
        availability_headers = {
            "content-type": "application/json", "cache-control": "private, no-store",
            "x-content-type-options": "nosniff",
        }
        html_headers = {
            "content-type": "text/html; charset=utf-8", "cache-control": "private, no-store",
            "x-content-type-options": "nosniff", "content-security-policy": "default-src 'none'",
            "referrer-policy": "strict-origin-when-cross-origin", "vary": "Accept",
        }
        response.side_effect = [
            (200, availability_headers, json.dumps({name: True for name in formats})),
            *[(200, html_headers, "<script>gamewiki-ad-start; invoke.js</script>") for _ in formats],
        ]
        self.assertEqual(_verify_online_advertising("https://game.example"), tuple(formats))

    @patch("publisher._http_response")
    def test_online_advertising_rejects_missing_security_header(self, response) -> None:
        response.return_value = (200, {"content-type": "application/json"}, "{}")
        with self.assertRaisesRegex(RuntimeError, "Cache-Control"):
            _verify_online_advertising("https://game.example")

    @patch("publisher._ensure_cloudflare_custom_domain")
    @patch("publisher._wait_cloudflare_deployment")
    @patch("publisher._cloudflare_create_git_deployment")
    @patch("publisher._set_cloudflare_project_environment")
    @patch("publisher.load_shared_ad_environment")
    @patch("publisher._resolve_cloudflare_project")
    def test_cloudflare_deploy_uses_git_integration(
        self, resolve_project, load_ads, set_environment, create_deployment, wait_deployment, ensure_domain
    ) -> None:
        resolve_project.return_value = ("game", self._git_project(), True)
        load_ads.return_value = {name: "encoded" for name in (
            "AD_NATIVE_BANNER_B64", "AD_NATIVE_BANNER_MOBILE_B64",
            "AD_BANNER_728X90_B64", "AD_BANNER_300X250_B64",
            "AD_BANNER_468X60_B64", "AD_SIDEBAR_160X600_B64",
            "AD_SIDEBAR_160X300_B64", "AD_MOBILE_320X50_B64",
        )}
        set_environment.return_value = ("NEXT_PUBLIC_SITE_URL", *load_ads.return_value)
        create_deployment.return_value = {"id": "deployment-id"}
        wait_deployment.return_value = {
            "id": "deployment-id",
            "url": "https://deploy.game.pages.dev",
            "deployment_trigger": {"metadata": {"commit_hash": "abc123"}},
            "latest_stage": {"status": "success"},
        }
        ensure_domain.return_value = {"name": "game.example", "status": "active"}
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
        set_environment.assert_called_once_with(
            "account",
            "hidden-token",
            "game",
            "https://game.example",
            load_ads.return_value,
            resolve_project.return_value[1],
        )
        wait_deployment.assert_called_once()
        self.assertEqual(len(result["environmentVariables"]), 9)
        self.assertEqual(result["adProfile"], "animal-hospital-anomalies.wiki")
        self.assertEqual(result["customDomain"], {"name": "game.example", "status": "active", "dns": None})

    def test_workers_static_assets_config_uses_worker_script_and_asset_binding(self) -> None:
        ads = {name: f"encoded-{index}" for index, name in enumerate((
            "AD_NATIVE_BANNER_B64",
            "AD_NATIVE_BANNER_MOBILE_B64",
            "AD_BANNER_728X90_B64",
            "AD_BANNER_300X250_B64",
            "AD_BANNER_468X60_B64",
            "AD_SIDEBAR_160X600_B64",
            "AD_SIDEBAR_160X300_B64",
            "AD_MOBILE_320X50_B64",
        ))}
        config = _workers_static_assets_config(
            "account",
            "game",
            "https://game.example",
            ads,
        )
        self.assertEqual(config["main"], "./src/worker.ts")
        self.assertEqual(config["assets"]["directory"], "./out")
        self.assertEqual(config["assets"]["binding"], "ASSETS")
        self.assertEqual(config["assets"]["html_handling"], "auto-trailing-slash")
        self.assertEqual(config["assets"]["not_found_handling"], "404-page")
        self.assertEqual(config["assets"]["run_worker_first"], ["/api/*"])
        self.assertEqual(config["vars"]["NEXT_PUBLIC_SITE_URL"], "https://game.example")
        self.assertEqual(config["vars"]["AD_MOBILE_320X50_B64"], ads["AD_MOBILE_320X50_B64"])

    def test_workers_static_assets_runtime_is_injected_for_existing_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "src").mkdir()
            (project / ".gitignore").write_text("node_modules\n", encoding="utf-8")

            changed = _ensure_workers_static_assets_runtime(project)

            self.assertIn("src/worker.ts", changed)
            self.assertIn(".gitignore", changed)
            self.assertTrue((project / "src" / "worker.ts").is_file())
            self.assertIn("/wrangler.jsonc", (project / ".gitignore").read_text(encoding="utf-8"))

    @patch("publisher._run_logged")
    @patch("publisher._ensure_cloudflare_worker_custom_domain")
    @patch("publisher._write_workers_static_assets_config")
    @patch("publisher.load_shared_ad_environment")
    @patch("publisher._cloudflare_workers_dev_origin")
    def test_workers_static_assets_deploy_uses_wrangler(
        self, workers_origin, load_ads, write_config, ensure_domain, run_logged
    ) -> None:
        workers_origin.return_value = "https://game.acct.workers.dev"
        load_ads.return_value = {name: "encoded" for name in (
            "AD_NATIVE_BANNER_B64", "AD_NATIVE_BANNER_MOBILE_B64",
            "AD_BANNER_728X90_B64", "AD_BANNER_300X250_B64",
            "AD_BANNER_468X60_B64", "AD_SIDEBAR_160X600_B64",
            "AD_SIDEBAR_160X300_B64", "AD_MOBILE_320X50_B64",
        )}
        write_config.return_value = Path("wrangler.jsonc")
        ensure_domain.return_value = {"name": "game.example", "status": "active"}
        run_logged.side_effect = [
            "build ok",
            "Uploaded assets\nhttps://game.acct.workers.dev",
        ]
        result = _deploy_cloudflare_workers_static_assets(
            Path("C:/game"),
            "game",
            "owner/game",
            "",
            "abc123",
            {"cf_accountid": "account", "cf_pages_api_key": "hidden-token"},
        )
        self.assertEqual(result["provider"], "cloudflare-workers-static-assets")
        self.assertEqual(result["deploymentMode"], "wrangler-static-assets")
        self.assertEqual(result["siteUrl"], "https://game.acct.workers.dev")
        self.assertEqual(result["deploymentUrl"], "https://game.acct.workers.dev")
        self.assertIsNone(result["customDomain"])
        ensure_domain.assert_not_called()
        self.assertEqual(len(result["environmentVariables"]), 9)
        self.assertEqual(run_logged.call_args_list[0].args[0][1:], ["run", "build"])
        build_env = run_logged.call_args_list[0].args[2]
        self.assertEqual(build_env["NEXT_PUBLIC_SITE_URL"], "https://game.acct.workers.dev")
        self.assertEqual(build_env["CF_WORKERS"], "1")
        self.assertEqual(
            run_logged.call_args_list[1].args[0][-3:],
            ["deploy", "--config", "wrangler.jsonc"],
        )
        deploy_env = run_logged.call_args_list[1].args[2]
        self.assertEqual(deploy_env["CLOUDFLARE_ACCOUNT_ID"], "account")
        self.assertEqual(deploy_env["CLOUDFLARE_API_TOKEN"], "hidden-token")

    @patch("publisher._run_logged")
    @patch("publisher._ensure_cloudflare_worker_custom_domain")
    @patch("publisher._write_workers_static_assets_config")
    @patch("publisher.load_shared_ad_environment")
    @patch("publisher._cloudflare_workers_dev_origin")
    def test_workers_static_assets_deploy_binds_custom_domain(
        self, workers_origin, load_ads, write_config, ensure_domain, run_logged
    ) -> None:
        workers_origin.return_value = "https://game.acct.workers.dev"
        load_ads.return_value = {name: "encoded" for name in (
            "AD_NATIVE_BANNER_B64", "AD_NATIVE_BANNER_MOBILE_B64",
            "AD_BANNER_728X90_B64", "AD_BANNER_300X250_B64",
            "AD_BANNER_468X60_B64", "AD_SIDEBAR_160X600_B64",
            "AD_SIDEBAR_160X300_B64", "AD_MOBILE_320X50_B64",
        )}
        write_config.return_value = Path("wrangler.jsonc")
        ensure_domain.return_value = {
            "name": "game.example",
            "status": "active",
            "dns": {"status": "managed", "target": "https://game.acct.workers.dev"},
        }
        run_logged.side_effect = [
            "build ok",
            "Uploaded assets\nhttps://game.acct.workers.dev",
        ]

        result = _deploy_cloudflare_workers_static_assets(
            Path("C:/game"),
            "game",
            "owner/game",
            "https://game.example/path",
            "abc123",
            {"cf_accountid": "account", "cf_pages_api_key": "hidden-token"},
        )

        self.assertEqual(result["siteUrl"], "https://game.example")
        self.assertEqual(result["customDomain"]["status"], "active")
        ensure_domain.assert_called_once_with(
            "account",
            "hidden-token",
            "game.example",
            "game",
            "https://game.acct.workers.dev",
        )

    @patch("publisher.time.sleep")
    @patch("publisher._cloudflare_global_request")
    @patch("publisher._cloudflare_request")
    def test_cloudflare_custom_domain_is_created_then_polled_to_active(self, request, global_request, _sleep) -> None:
        request.side_effect = [
            RuntimeError("HTTP 404 from domain"),
            {"name": "game.example", "status": "pending"},
            {"name": "game.example", "status": "active"},
        ]
        global_request.side_effect = [
            [{"id": "zone-id", "name": "example", "status": "active"}],
            [],
            {"id": "record-id"},
        ]
        result = _ensure_cloudflare_custom_domain(
            "account", "token", "game", "https://game.example", "https://game.pages.dev", attempts=2, interval_seconds=0,
        )
        self.assertEqual(result["status"], "active")
        self.assertEqual(request.call_args_list[1].args[0], "POST")
        self.assertEqual(request.call_args_list[1].args[3], "pages/projects/game/domains")
        self.assertEqual(request.call_args_list[1].args[4], {"name": "game.example"})
        self.assertEqual(result["dns"]["status"], "created")
        self.assertEqual(global_request.call_args_list[2].args[0], "POST")
        self.assertEqual(global_request.call_args_list[2].args[3]["content"], "game.pages.dev")

    @patch("publisher._cloudflare_request")
    @patch("publisher._cloudflare_global_request")
    def test_cloudflare_custom_domain_skips_pages_binding_when_dns_is_not_ready(self, global_request, request) -> None:
        request.side_effect = [RuntimeError("HTTP 404 from domain")]
        global_request.return_value = []
        result = _ensure_cloudflare_custom_domain(
            "account", "token", "game", "https://game.example", "https://game.pages.dev", attempts=1, interval_seconds=0,
        )
        self.assertEqual(result["status"], "not_requested")
        self.assertEqual(result["dns"]["status"], "missing_zone")
        self.assertEqual(len(request.call_args_list), 1)

    @patch("publisher._cloudflare_global_request")
    def test_cloudflare_dns_cname_does_not_overwrite_existing_records(self, global_request) -> None:
        global_request.side_effect = [
            [{"id": "zone-id", "name": "example", "status": "active"}],
            [{"id": "dns-id", "type": "CNAME", "content": "old.example.net"}],
        ]
        result = _ensure_cloudflare_dns_cname("account", "token", "game.example", "game.pages.dev")
        self.assertEqual(result["status"], "blocked_existing_record")
        self.assertEqual(global_request.call_count, 2)

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
            json.dumps({"release": "v1_0730"}), encoding="utf-8"
        )
        return root

    def test_complete_project_is_publishable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = _validate_project(self._project(Path(temporary)))
        self.assertEqual(manifest["status"], "complete")

    def test_previous_release_cannot_publish_as_current(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self._project(Path(temporary))
            (project / "intake" / "factory-release.json").write_text(
                json.dumps({"release": "v1_0728"}), encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "expected 'v1_0730'"):
                _validate_project(project)

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

    def test_github_remote_url_normalization_accepts_https_and_ssh(self) -> None:
        self.assertEqual(
            _github_repo_from_remote_url("https://github.com/Owner/Game.git"),
            "owner/game",
        )
        self.assertEqual(
            _github_repo_from_remote_url("git@github.com:Owner/Game.git"),
            "owner/game",
        )
        self.assertEqual(
            _github_repo_from_remote_url("https://token@github.com/Owner/Game"),
            "owner/game",
        )

    @patch("publisher._run")
    def test_origin_remote_must_match_target_repo(self, run) -> None:
        run.side_effect = ["origin\n", "https://github.com/other/game.git"]
        with self.assertRaisesRegex(RuntimeError, "origin remote does not match"):
            _ensure_origin_remote(Path("C:/game"), "owner/game", {})

    @patch("publisher._run")
    def test_missing_origin_remote_is_added_for_target_repo(self, run) -> None:
        run.return_value = "backup\n"
        _ensure_origin_remote(Path("C:/game"), "owner/game", {})
        self.assertEqual(
            run.call_args_list[-1].args[0],
            ["git", "remote", "add", "origin", "https://github.com/owner/game.git"],
        )

    @patch("publisher._run", return_value="declanliang\t130889021")
    def test_git_author_uses_authenticated_github_noreply_identity(self, run) -> None:
        author = _resolve_git_author(Path("C:/game"), {"GH_TOKEN": "hidden"})
        self.assertEqual(author, ("declanliang", "130889021+declanliang@users.noreply.github.com"))
        self.assertNotIn("hidden", run.call_args.args[0])

    @patch("publisher._verify_online_advertising", return_value=("nativeBanner", "nativeBannerMobile", "banner728x90", "banner300x250", "banner468x60", "sidebar160x600", "sidebar160x300", "mobile320x50"))
    @patch("publisher.shutil.which", return_value="npm")
    @patch("publisher.subprocess.run")
    def test_online_verification_is_a_logged_publish_postcondition(self, run, _which, ads) -> None:
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
        self.assertEqual(result["advertising"]["formats"], list(ads.return_value))

    @patch("publisher.shutil.which", return_value="npm")
    @patch("publisher.subprocess.run")
    def test_online_verification_failure_blocks_publish(self, run, _which) -> None:
        run.return_value.returncode = 1
        run.return_value.stdout = "online sitemap target returned 404"
        run.return_value.stderr = ""
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, "online deployment verification failed"):
                _verify_online_deployment(project, "https://game.example", {}, attempts=1)
            self.assertTrue((project / ".gamewiki" / "deploy-verification.log").is_file())


if __name__ == "__main__":
    unittest.main()
