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
)


class ProjectContractTests(unittest.TestCase):
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
        self.assertLessEqual(len(ids), 8)
        self.assertIn("enemies", ids)
        self.assertIn("floors", ids)
        self.assertIn("upgrades", ids)
        self.assertIn("economy", ids)

    def test_site_plan_maps_strategy_to_guide_without_synthetic_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = build_game_profile(self._basic_output(Path(temporary)))
        raw = {
            "categories": [
                {"category": "guide", "keywords": ["hellhole guide"]},
                {"category": "strategy", "keywords": ["hellhole tips and tricks"]},
                {"category": "codes", "keywords": ["unverified code"]},
            ]
        }
        plan = build_site_plan(profile, raw)
        self.assertEqual([item["id"] for item in plan["categories"]], ["guide"])
        self.assertEqual(
            plan["categories"][0]["keywords"],
            ["hellhole guide", "hellhole tips and tricks"],
        )
        self.assertNotIn(
            "site-plan-relevant-fallback",
            [source for item in plan["categories"] for source in item["sources"]],
        )
        self.assertNotIn("codes", [item["id"] for item in plan["categories"]])
        self.assertEqual(build_seo_keywords(plan)["languages"], FIXED_LANGUAGES[1:])

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
