from __future__ import annotations

import sys
import unittest
from pathlib import Path


SEO_SCOUT_ROOT = Path(__file__).resolve().parents[1] / "pipeline" / "seo-scout"
sys.path.insert(0, str(SEO_SCOUT_ROOT))

from seoscout.generate import is_evidence_limited_rejection, validate_markdown  # noqa: E402


def article(body: str) -> str:
    return (
        'export const metadata = {\n'
        '  title: "Evidence-backed guide",\n'
        '  description: "A complete evidence-backed description for this focused game guide.",\n'
        '  category: "guide",\n'
        '  date: "2026-07-28",\n'
        '}\n\n'
        + body
        + "\n"
    )


class FactGuardTests(unittest.TestCase):
    def test_only_speculation_density_is_an_evidence_limited_rejection(self) -> None:
        self.assertTrue(
            is_evidence_limited_rejection(
                "Speculation density is too high (4 markers); omit unsupported filler"
            )
        )
        self.assertTrue(
            is_evidence_limited_rejection(
                "Unsupported positive Steam Deck rating — controller support does not prove Verified or Playable"
            )
        )
        self.assertFalse(is_evidence_limited_rejection("Missing or too short BODY section"))
        self.assertFalse(is_evidence_limited_rejection(None))

    def test_rejects_inferred_positive_steam_deck_rating(self) -> None:
        valid, error = validate_markdown(
            article("## Compatibility\nSteam Deck is Verified because the game has full controller support. " * 3)
        )
        self.assertFalse(valid)
        self.assertIn("Steam Deck", error)

    def test_allows_explicitly_unconfirmed_deck_status(self) -> None:
        valid, error = validate_markdown(
            article(
                "## Compatibility\nThe Steam Deck Verified status is unconfirmed. "
                "Full controller support does not establish an official Deck rating. "
                "Players should verify the current store badge before buying."
            )
        )
        self.assertTrue(valid, error)

    def test_rejects_speculation_padding(self) -> None:
        body = "## Unknown systems\n" + " ".join(
            ["This might change.", "It could appear.", "That is likely."]
        )
        valid, error = validate_markdown(article(body))
        self.assertFalse(valid)
        self.assertIn("Speculation density", error)

    def test_allows_one_explicitly_unconfirmed_note(self) -> None:
        valid, error = validate_markdown(
            article(
                "## Current evidence\n"
                "The exact unlock condition is unconfirmed. Check the current in-game objective text before planning a run."
            )
        )
        self.assertTrue(valid, error)

    def test_rejects_future_tense_for_release_date_that_has_passed(self) -> None:
        valid, error = validate_markdown(
            article(
                "## Release date\n"
                "The game will launch on July 16, 2026. "
                "Use the official store page to review platforms and current availability."
            )
        )
        self.assertFalse(valid)
        self.assertIn("Stale release-state tense", error)

    def test_accepts_past_tense_for_release_date_that_has_passed(self) -> None:
        valid, error = validate_markdown(
            article(
                "## Release date\n"
                "The game launched on July 16, 2026. "
                "Use the official store page to review platforms and current availability."
            )
        )
        self.assertTrue(valid, error)


if __name__ == "__main__":
    unittest.main()
