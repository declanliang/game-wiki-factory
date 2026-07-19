from __future__ import annotations

import unittest
from unittest.mock import patch

from get_search.collectors import GOOGLE_SUGGEST_ENDPOINT, collect_google_suggest
from get_search.config import Settings


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return b'["Anime Paradox X", ["anime paradox x codes", "anime paradox x tier list"]]'


class GoogleSuggestTests(unittest.TestCase):
    @patch("get_search.collectors.time.sleep")
    @patch("get_search.collectors.urllib.request.urlopen", return_value=_Response())
    def test_collects_firefox_json_without_api_key(self, urlopen, _sleep) -> None:
        settings = Settings(api_login="unused", api_password="unused", timeout_seconds=5)
        result = collect_google_suggest(
            "Anime Paradox X", settings, include_az=False
        )

        self.assertEqual(result["source"], "google-direct")
        self.assertEqual(result["endpoint"], GOOGLE_SUGGEST_ENDPOINT)
        self.assertEqual(result["cost"], 0.0)
        self.assertEqual(len(result["queries"]), 1)
        self.assertEqual(len(result["unique_suggestions"]), 2)
        self.assertEqual(
            [item["suggestion"] for item in result["queries"][0]["suggestions"]],
            ["anime paradox x codes", "anime paradox x tier list"],
        )
        self.assertIn("client=firefox", urlopen.call_args.args[0].full_url)


if __name__ == "__main__":
    unittest.main()
