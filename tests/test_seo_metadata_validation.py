from __future__ import annotations

import sys
import unittest
from pathlib import Path


SEO_SCOUT_ROOT = Path(__file__).resolve().parents[1] / "pipeline" / "seo-scout"
sys.path.insert(0, str(SEO_SCOUT_ROOT))

from seoscout.generate import _process_llm_response as process_english, page_type_brief
from seoscout.translate import (
    _build_mdx as build_translation_mdx,
    _process_llm_response as process_translation,
    deduplicate_translated_titles,
)


BODY = "## Practical Steps\n\n" + ("Use this evidence-backed tactic during each round. " * 12)
DESCRIPTION = "Learn practical movement, timing, and positioning tips that help new players understand each round and make better decisions."


class SeoMetadataValidationTests(unittest.TestCase):
    def test_page_type_brief_preserves_entity_intent(self) -> None:
        brief = page_type_brief(
            {"pageType": "entity", "entityName": "Akaza", "entityType": "unit", "intent": "How to obtain Akaza"},
            "characters",
        )
        self.assertIn("focused named-entity", brief)
        self.assertIn("Entity: Akaza", brief)
        self.assertIn("How to obtain Akaza", brief)

    def test_accepts_compact_english_serp_metadata(self) -> None:
        raw = f"TITLE: Timebomb Duels Tips: Movement and Positioning\nDESCRIPTION: {DESCRIPTION}\nBODY:\n{BODY}"
        content, error = process_english(raw, "guide", "2026-07-19")
        self.assertIsNotNone(content, error)

    def test_compacts_overlong_english_title(self) -> None:
        title = "Timebomb Duels Ultimate Complete Strategy Guide for Every New Player"
        raw = f"TITLE: {title}\nDESCRIPTION: {DESCRIPTION}\nBODY:\n{BODY}"
        content, error = process_english(raw, "guide", "2026-07-19")
        self.assertIsNotNone(content, error)

    def test_rejects_a_second_output_contract_embedded_in_article_body(self) -> None:
        repeated = (
            f"TITLE: Timebomb Duels Tips\nDESCRIPTION: {DESCRIPTION}\nBODY:\n{BODY}"
            f"\nTITLE: Timebomb Duels Tips\nDESCRIPTION: {DESCRIPTION}\nBODY:\n{BODY}"
        )
        content, error = process_english(repeated, "guide", "2026-07-19")
        self.assertIsNone(content)
        self.assertIn("Duplicated TITLE/DESCRIPTION/BODY", error)

    def test_normalizes_basic_raw_html_blocks_before_saving_mdx(self) -> None:
        body = "<h2>Maps</h2>\n<ul><li><h3>Facility</h3>Use cover carefully.</li></ul>\n" + BODY
        raw = f"TITLE: Dino Hunters Maps\nDESCRIPTION: {DESCRIPTION}\nBODY:\n{body}"
        content, error = process_english(raw, "floors", "2026-07-21")
        self.assertIsNotNone(content, error)
        self.assertIn("## Maps", content)
        self.assertIn("### Facility", content)
        self.assertNotIn("<li>", content)
        metadata_title = content.split('title: ', 1)[1].splitlines()[0]
        self.assertLessEqual(len(metadata_title) - 3, 60)

    def test_compacts_overlong_english_description(self) -> None:
        description = DESCRIPTION + " Extra words that do not change the underlying claim."
        raw = f"TITLE: Timebomb Duels Tips\nDESCRIPTION: {description}\nBODY:\n{BODY}"
        content, error = process_english(raw, "guide", "2026-07-19")
        self.assertIsNotNone(content, error)

    def test_compacted_english_title_does_not_end_with_ampersand(self) -> None:
        title = "Animal Hospital Anomaly Roblox Beginner Tips: Survive & Escape Every Shift"
        raw = f"TITLE: {title}\nDESCRIPTION: {DESCRIPTION}\nBODY:\n{BODY}"
        content, error = process_english(raw, "guide", "2026-07-19")
        self.assertIsNotNone(content, error)
        metadata_title = content.split("title: ", 1)[1].splitlines()[0]
        self.assertNotRegex(metadata_title, r"&[\"']?,?$")

    def test_rejects_overlong_cjk_translation_title(self) -> None:
        title = "時限爆弾デュエルで勝つための初心者向け完全攻略と移動テクニック徹底解説ガイド"
        raw = f"TITLE: {title}\nDESCRIPTION: 実践的な移動と位置取りを学べる初心者向け攻略です。\nBODY:\n{BODY}"
        content, error = process_translation(raw, "guide", "2026-07-19", lang_code="ja")
        self.assertIsNone(content)
        self.assertIn("maximum 36", error)

    def test_disambiguates_duplicate_translated_titles_without_touching_body(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [
                root / "ja" / "items" / "game-roblox-strange-egg.mdx",
                root / "ja" / "guide" / "game-roblox-clean-items.mdx",
            ]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    build_translation_mdx("ゲーム攻略", "説明です。", path.parent.name, "2026-07-21", BODY),
                    encoding="utf-8",
                )
            changed = deduplicate_translated_titles(root, ["ja"])
            self.assertEqual(changed, 2)
            contents = [path.read_text(encoding="utf-8") for path in paths]
            titles = [content.split("title: ", 1)[1].splitlines()[0] for content in contents]
            self.assertEqual(len(set(titles)), 2)
            self.assertTrue(all("## Practical Steps" in content for content in contents))
            self.assertTrue(all("Use this evidence-backed tactic" in content for content in contents))


if __name__ == "__main__":
    unittest.main()
