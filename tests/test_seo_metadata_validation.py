from __future__ import annotations

import sys
import unittest
from pathlib import Path


SEO_SCOUT_ROOT = Path(__file__).resolve().parents[1] / "pipeline" / "seo-scout"
sys.path.insert(0, str(SEO_SCOUT_ROOT))

from seoscout.generate import _process_llm_response as process_english
from seoscout.translate import _process_llm_response as process_translation


BODY = "## Practical Steps\n\n" + ("Use this evidence-backed tactic during each round. " * 12)
DESCRIPTION = "Learn practical movement, timing, and positioning tips that help new players understand each round and make better decisions."


class SeoMetadataValidationTests(unittest.TestCase):
    def test_accepts_compact_english_serp_metadata(self) -> None:
        raw = f"TITLE: Timebomb Duels Tips: Movement and Positioning\nDESCRIPTION: {DESCRIPTION}\nBODY:\n{BODY}"
        content, error = process_english(raw, "guide", "2026-07-19")
        self.assertIsNotNone(content, error)

    def test_compacts_overlong_english_title(self) -> None:
        title = "Timebomb Duels Ultimate Complete Strategy Guide for Every New Player"
        raw = f"TITLE: {title}\nDESCRIPTION: {DESCRIPTION}\nBODY:\n{BODY}"
        content, error = process_english(raw, "guide", "2026-07-19")
        self.assertIsNotNone(content, error)
        metadata_title = content.split('title: ', 1)[1].splitlines()[0]
        self.assertLessEqual(len(metadata_title) - 3, 60)

    def test_compacts_overlong_english_description(self) -> None:
        description = DESCRIPTION + " Extra words that do not change the underlying claim."
        raw = f"TITLE: Timebomb Duels Tips\nDESCRIPTION: {description}\nBODY:\n{BODY}"
        content, error = process_english(raw, "guide", "2026-07-19")
        self.assertIsNotNone(content, error)

    def test_rejects_overlong_cjk_translation_title(self) -> None:
        title = "時限爆弾デュエルで勝つための初心者向け完全攻略と移動テクニック徹底解説ガイド"
        raw = f"TITLE: {title}\nDESCRIPTION: 実践的な移動と位置取りを学べる初心者向け攻略です。\nBODY:\n{BODY}"
        content, error = process_translation(raw, "guide", "2026-07-19", lang_code="ja")
        self.assertIsNone(content)
        self.assertIn("maximum 36", error)


if __name__ == "__main__":
    unittest.main()
