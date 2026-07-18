from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from get_search.classifier import Candidate
from get_search.manual_inputs import load_manual_inputs, merge_manual_candidates


class ManualInputTests(unittest.TestCase):
    def test_loads_similarweb_and_google_suggest_formats(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "similarweb.csv").write_text(
                "关键词\nanime expeditions\nanime expeditions codes\nunit (anime expeditions)\n",
                encoding="utf-8-sig",
            )
            (folder / "google-suggest.txt").write_text(
                "# one keyword per line\nanime expeditions tier list\nanime expeditions script\n",
                encoding="utf-8",
            )
            candidates, rejected, summary = load_manual_inputs(
                "Anime Expeditions", folder
            )
        keywords = {item.keyword for item in candidates}
        self.assertEqual(
            keywords,
            {
                "anime expeditions codes",
                "anime expeditions unit",
                "anime expeditions tier list",
            },
        )
        self.assertEqual(summary["raw_keywords"], 5)
        self.assertEqual(summary["accepted_keywords"], 3)
        self.assertEqual(summary["rejected_keywords"], 2)
        self.assertEqual(len(rejected), 2)

    def test_manual_source_merges_with_automatic_candidate(self) -> None:
        automatic = [
            Candidate(
                keyword="anime expeditions codes",
                sources={"autocomplete"},
                autocomplete_occurrences=1,
            )
        ]
        manual = [
            Candidate(
                keyword="anime expeditions codes",
                sources={"similarweb"},
                evidence=["anime expeditions codes"],
            )
        ]
        merged = merge_manual_candidates("Anime Expeditions", automatic, manual)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].sources, {"autocomplete", "similarweb"})
        self.assertGreater(merged[0].score, 0)

    def test_loads_google_trends_top_and_rising_exports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "searched_with_top-searches_US_test.csv").write_text(
                '"query","search interest","increase percent"\n'
                '"anime expeditions codes",100,"100%"\n',
                encoding="utf-8",
            )
            (folder / "searched_with_rising-searches_US_test.csv").write_text(
                '"query","search interest","increase percent"\n'
                '"anime expeditions tier list",20,"Breakout"\n',
                encoding="utf-8",
            )

            candidates, rejected, summary = load_manual_inputs(
                "Anime Expeditions", folder
            )

            self.assertFalse(rejected)
            by_keyword = {item.keyword: item for item in candidates}
            self.assertEqual(by_keyword["anime expeditions codes"].trends_top, 100)
            self.assertEqual(by_keyword["anime expeditions tier list"].trends_rising, 20)
            self.assertEqual(summary["accepted_keywords"], 2)


if __name__ == "__main__":
    unittest.main()
