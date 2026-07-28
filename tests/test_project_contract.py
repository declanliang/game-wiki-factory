from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from project_contract import (
    FIXED_LANGUAGES,
    build_game_profile,
    build_seo_keywords,
    build_site_plan,
    reconcile_site_plan,
    render_project_readme,
)


class ProjectContractTests(unittest.TestCase):
    def test_named_reward_loop_keeps_economy_inside_basic_info_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            intake = output / "template-intake"
            intake.mkdir()
            (intake / "site-identity.json").write_text(json.dumps({
                "GAME_NAME": "Incremental Game",
                "OFFICIAL_GAME_URL": "https://www.roblox.com/games/1/game",
                "LANGUAGES": ["en", "es", "de", "fr", "ja"],
            }), encoding="utf-8")
            (intake / "site-content.json").write_text(json.dumps({
                "site": {"description": "Earn Stars, buy upgrades, and climb.", "gamePlatform": ["Roblox"]},
            }), encoding="utf-8")
            profile = build_game_profile(output)
        self.assertIn("economy", [item["id"] for item in profile["categoryCandidates"]])

    def test_steam_project_readme_preserves_deterministic_resume_command(self) -> None:
        url = "https://store.steampowered.com/app/3712080/funnel_runners/"
        readme = render_project_readme("Funnel Runners", "Steam", url)
        self.assertIn(f'--platform steam --official-url "{url}"', readme)
        self.assertIn("full controller support", readme)

    def _basic_output(self, root: Path) -> Path:
        intake = root / "template-intake"
        intake.mkdir(parents=True)
        (intake / "site-identity.json").write_text(
            json.dumps({"GAME_NAME": "Hellhole", "OFFICIAL_GAME_URL": "https://www.roblox.com/games/1/x", "LANGUAGES": FIXED_LANGUAGES}),
            encoding="utf-8",
        )
        (intake / "site-content.json").write_text(
            json.dumps({"site": {"description": "Fight enemy hordes, open loot, stack upgrades, and descend deeper floors."}}),
            encoding="utf-8",
        )
        (root / "facts.json").write_text(
            json.dumps({"game": {"officialDescription": "Shoot the horde and descend the shaft for loot and upgrades."}}),
            encoding="utf-8",
        )
        return root

    def test_basic_info_owns_category_boundary_and_fixed_languages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = build_game_profile(self._basic_output(Path(temporary)))
        ids = [item["id"] for item in profile["categoryCandidates"]]
        self.assertEqual(profile["languages"], FIXED_LANGUAGES)
        self.assertGreaterEqual(len(ids), 4)
        self.assertLessEqual(len(ids), 16)
        self.assertIn("enemies", ids)
        self.assertIn("floors", ids)
        self.assertIn("upgrades", ids)
        self.assertIn("economy", ids)
        self.assertIn("codes", ids)
        for candidate in profile["categoryCandidates"]:
            self.assertEqual(list(candidate["descriptions"]), FIXED_LANGUAGES)
            self.assertTrue(all(candidate["descriptions"].values()))

    def test_site_plan_maps_strategy_to_guide_without_synthetic_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = build_game_profile(self._basic_output(Path(temporary)))
        raw = {
            "categories": [
                {"category": "guide", "keywords": ["hellhole guide"]},
                {"category": "strategy", "keywords": ["hellhole tips and tricks"]},
                {"category": "pets", "keywords": ["unverified pets"]},
            ]
        }
        plan = build_site_plan(profile, raw)
        self.assertEqual([item["id"] for item in plan["categories"]], ["guide"])
        self.assertEqual(
            plan["categories"][0]["keywords"],
            ["hellhole guide", "hellhole tips and tricks"],
        )
        self.assertEqual(list(plan["categories"][0]["descriptions"]), FIXED_LANGUAGES)
        self.assertNotIn(
            "site-plan-relevant-fallback",
            [source for item in plan["categories"] for source in item["sources"]],
        )
        self.assertNotIn("pets", [item["id"] for item in plan["categories"]])
        self.assertEqual(build_seo_keywords(plan)["languages"], FIXED_LANGUAGES[1:])

    def test_rankable_entities_enable_tier_list_and_topic_metadata_survives(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._basic_output(Path(temporary))
            content_path = root / "template-intake" / "site-content.json"
            content_path.write_text(
                json.dumps({"site": {"description": "Collect units, evolve characters, and compare traits."}}),
                encoding="utf-8",
            )
            profile = build_game_profile(root)
        ids = [item["id"] for item in profile["categoryCandidates"]]
        self.assertIn("characters", ids)
        self.assertIn("tier-list", ids)
        raw = {
            "categories": [{
                "category": "tier-list",
                "keywords": ["hellhole unit tier list"],
                "topics": [{
                    "keyword": "hellhole unit tier list",
                    "pageType": "tier_list",
                    "intent": "Compare the strongest units",
                    "confidence": 0.88,
                    "discoverySources": ["context-opportunity", "official"],
                    "evidenceUrls": ["https://example.com/official"],
                }],
            }],
        }
        plan = build_site_plan(profile, raw)
        self.assertEqual(plan["schemaVersion"], 2)
        topic = plan["categories"][0]["topics"][0]
        self.assertEqual(topic["pageType"], "tier_list")
        self.assertEqual(topic["primaryKeyword"], "hellhole unit tier list")
        self.assertEqual(topic["researchQuery"], "Roblox hellhole unit tier list")
        self.assertEqual(topic["userQuestion"], "Compare the strongest units")
        self.assertEqual(topic["mustAnswer"], ["Compare the strongest units"])
        self.assertEqual(topic["demandClass"], "evidence-backed")
        self.assertIn("Limited shared background", topic["overlapPolicy"])
        bridge = build_seo_keywords(plan)
        self.assertEqual(bridge["topic_specs"]["hellhole unit tier list"]["pageType"], "tier_list")
        self.assertEqual(
            bridge["topic_specs"]["hellhole unit tier list"]["userQuestion"],
            "Compare the strongest units",
        )

    def test_site_plan_rejects_an_empty_evidence_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = build_game_profile(self._basic_output(Path(temporary)))
        with self.assertRaisesRegex(ValueError, "did not deliver any evidence-backed"):
            build_site_plan(profile, {"categories": []})

    def test_reconcile_marks_only_delivered_categories_published(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = build_game_profile(self._basic_output(root / "basic"))
            raw = {"categories": [
                {"category": "guide", "keywords": ["a"]},
                {"category": "enemies", "keywords": ["b"]},
                {"category": "floors", "keywords": ["c"]},
                {"category": "upgrades", "keywords": ["d"]},
            ]}
            plan = build_site_plan(profile, raw)
            articles = root / "articles" / "en"
            for category in ("guide", "enemies", "floors", "upgrades"):
                target = articles / category
                target.mkdir(parents=True)
                (target / "one.mdx").write_text("x", encoding="utf-8")
            reconciled = reconcile_site_plan(plan, root / "articles")
        self.assertEqual(reconciled["qualityGate"]["publishedCategoryCount"], 4)


if __name__ == "__main__":
    unittest.main()
