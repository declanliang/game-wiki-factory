from __future__ import annotations

import base64
import json
import unittest
from unittest.mock import patch

from locale_publication import publish_locale_in_github
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
