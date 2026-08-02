from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from locale_publication import publish_locale_in_github, release_locale
from publication_plan import build_publication_plan


class LocalePublicationTests(unittest.TestCase):
    @patch("locale_publication._github_request")
    def test_locale_release_updates_only_next_locale(self, request) -> None:
        plan = build_publication_plan()
        request.side_effect = [
            {
                "sha": "blob-sha",
                "content": base64.b64encode(
                    json.dumps(plan).encode("utf-8")
                ).decode("ascii"),
            },
            {"commit": {"sha": "commit-sha"}},
        ]

        updated, commit_sha, changed = publish_locale_in_github(
            "hidden-token", "owner/game", "es"
        )

        self.assertTrue(changed)
        self.assertEqual(commit_sha, "commit-sha")
        self.assertEqual(updated["publishedLocales"], ["en", "es"])
        put_payload = request.call_args_list[1].args[3]
        committed_plan = json.loads(
            base64.b64decode(put_payload["content"]).decode("utf-8")
        )
        self.assertEqual(committed_plan["publishedLocales"], ["en", "es"])
        self.assertNotIn("hidden-token", json.dumps(put_payload))

    @patch("locale_publication._github_request")
    def test_locale_release_rejects_skipped_wave(self, request) -> None:
        plan = build_publication_plan()
        request.return_value = {
            "sha": "blob-sha",
            "content": base64.b64encode(
                json.dumps(plan).encode("utf-8")
            ).decode("ascii"),
        }
        with self.assertRaisesRegex(RuntimeError, "expected es"):
            publish_locale_in_github("hidden-token", "owner/game", "de")

    @patch("locale_publication.verify_locale_deployment")
    @patch("locale_publication._deploy_cloudflare_workers_static_assets")
    @patch("locale_publication._clone_locale_release_workspace")
    @patch("locale_publication.publish_locale_in_github")
    @patch("locale_publication._github_token")
    @patch("locale_publication.build_subprocess_env")
    def test_release_locale_redeploys_workers_static_assets(
        self,
        build_env,
        github_token,
        publish_plan,
        clone_workspace,
        deploy_workers,
        verify_deployment,
    ) -> None:
        build_env.return_value = {
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "CLOUDFLARE_API_TOKEN": "cloudflare-token",
        }
        github_token.return_value = "github-token"
        publish_plan.return_value = (
            {"publishedLocales": ["en", "es"]},
            "commit-sha",
            True,
        )
        clone_workspace.return_value = Path("C:/tmp/game")
        deploy_workers.return_value = {
            "provider": "cloudflare-workers-static-assets",
            "deploymentUrl": "https://game.account.workers.dev",
            "workersDevOrigin": "https://game.account.workers.dev",
            "deploymentId": None,
        }
        verify_deployment.return_value = {"status": "complete"}

        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.json"
            result = Path(temporary) / "result.json"
            config.write_text(
                json.dumps({
                    "taskType": "localeRelease",
                    "locale": "es",
                    "githubRepo": "owner/game",
                    "workerName": "game",
                    "siteUrl": "https://game.example",
                    "workersDevOrigin": "https://game.account.workers.dev",
                }),
                encoding="utf-8",
            )

            self.assertEqual(release_locale(["--config", str(config), "--result", str(result)]), 0)
            payload = json.loads(result.read_text(encoding="utf-8"))

        deploy_workers.assert_called_once_with(
            clone_workspace.return_value,
            "game",
            "owner/game",
            "https://game.example",
            "commit-sha",
            {
                "CLOUDFLARE_ACCOUNT_ID": "account",
                "CLOUDFLARE_API_TOKEN": "cloudflare-token",
                "GH_TOKEN": "github-token",
            },
        )
        verify_deployment.assert_called_once_with(
            "https://game.account.workers.dev",
            "https://game.example",
            ["en", "es"],
        )
        self.assertEqual(payload["hosting"]["provider"], "cloudflare-workers-static-assets")
        self.assertEqual(payload["hosting"]["workerName"], "game")
