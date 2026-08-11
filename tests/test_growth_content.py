from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from growth_content import (
    build_growth_seo_keywords,
    merge_growth_articles,
    normalize_growth_config,
    select_new_proposals,
    update_site_plan_with_growth,
)


def _site_plan() -> dict:
    return {
        "game": {"name": "Example Game", "platform": "Roblox"},
        "languages": ["en"],
        "categories": [
            {
                "id": "guide",
                "status": "published",
                "description": "How-to guides",
                "keywords": ["Example Game beginner guide"],
                "topics": [],
                "articleCount": 1,
                "sources": ["guide-search"],
            },
            {
                "id": "codes",
                "status": "unfulfilled",
                "description": "Codes",
                "keywords": ["Example Game codes"],
                "topics": [],
                "articleCount": 0,
            },
        ],
    }


class GrowthContentTests(unittest.TestCase):
    def test_normalize_growth_config_accepts_create_article_only(self) -> None:
        config = normalize_growth_config({
            "taskType": "siteGrowthContent",
            "slug": "Example Game",
            "publish": False,
            "proposals": [
                {"keyword": "Example Game best routes", "targetCategory": "Guide"}
            ],
        })
        self.assertEqual(config["slug"], "example-game")
        self.assertFalse(config["publish"])
        self.assertEqual(config["proposals"][0]["targetCategory"], "guide")

        with self.assertRaisesRegex(ValueError, "create_article"):
            normalize_growth_config({
                "taskType": "siteGrowthContent",
                "slug": "example-game",
                "proposals": [
                    {"action": "translate_es", "keyword": "Example Game guía", "targetCategory": "guide"}
                ],
            })

    def test_select_new_proposals_requires_existing_published_category(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "content" / "en" / "guide").mkdir(parents=True)
            (project / "content" / "en" / "guide" / "example-game-best-routes.mdx").write_text(
                "export const metadata = {}\n",
                encoding="utf-8",
            )
            config = normalize_growth_config({
                "taskType": "siteGrowthContent",
                "slug": "example-game",
                "proposals": [
                    {"keyword": "Example Game best routes", "targetCategory": "guide"},
                    {"keyword": "Example Game codes", "targetCategory": "codes"},
                    {"keyword": "Example Game late game guide", "targetCategory": "guide"},
                ],
            })
            accepted, skipped = select_new_proposals(config, _site_plan(), project)
        self.assertEqual([item["keyword"] for item in accepted], ["Example Game late game guide"])
        self.assertEqual(
            [item["reason"].split(":")[0] for item in skipped],
            ["article-exists", "category-not-published"],
        )

    def test_build_growth_seo_keywords_is_english_only(self) -> None:
        proposals = [
            {
                "keyword": "Example Game late game guide",
                "targetCategory": "guide",
                "intent": "How should players approach late game?",
                "reason": "GSC shows high impressions.",
                "evidence": {"confidence": "high", "urls": ["https://example.test/source"]},
            }
        ]
        keywords = build_growth_seo_keywords(_site_plan(), proposals)
        self.assertEqual(keywords["languages"], [])
        self.assertEqual(keywords["categories"][0]["category"], "guide")
        self.assertIn("Example Game late game guide", keywords["topic_specs"])
        self.assertEqual(
            keywords["topic_specs"]["Example Game late game guide"]["demandClass"],
            "gsc-backed",
        )

    def test_merge_articles_updates_intake_and_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated = root / "generated"
            source = generated / "en" / "guide" / "example-game-late-game-guide.mdx"
            source.parent.mkdir(parents=True)
            source.write_text("export const metadata = {}\n# Guide\n", encoding="utf-8")
            proposals = [
                {
                    "keyword": "Example Game late game guide",
                    "targetCategory": "guide",
                    "slug": "example-game-late-game-guide",
                }
            ]
            added = merge_growth_articles(generated, root / "intake" / "articles", root / "content", proposals)
            self.assertEqual(added[0]["path"], "en/guide/example-game-late-game-guide.mdx")
            self.assertTrue((root / "intake" / "articles" / "en" / "guide" / source.name).is_file())
            self.assertTrue((root / "content" / "en" / "guide" / source.name).is_file())

    def test_update_site_plan_records_growth_keyword(self) -> None:
        updated = update_site_plan_with_growth(
            _site_plan(),
            [
                {
                    "keyword": "Example Game late game guide",
                    "targetCategory": "guide",
                    "intent": "How should players approach late game?",
                }
            ],
        )
        guide = updated["categories"][0]
        self.assertIn("Example Game late game guide", guide["keywords"])
        self.assertIn("growth-agent", guide["sources"])
        self.assertEqual(guide["articleCount"], 2)


if __name__ == "__main__":
    unittest.main()

