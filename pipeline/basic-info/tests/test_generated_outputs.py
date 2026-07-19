from __future__ import annotations

import json
import copy
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from gamewiki_automation.schemas import HOMEPAGE_SCHEMA, MODULES_SCHEMA, TEMPLATE_SITE_CONTENT_SCHEMA, TEMPLATE_SITE_IDENTITY_SCHEMA
from gamewiki_automation.template_contract import validate_localized_site_content, validate_site_content, validate_site_identity


ROOT = Path(__file__).resolve().parents[1]


class GeneratedOutputTests(unittest.TestCase):
    def _check(self, slug: str, place_id: str):
        directory = ROOT / "output" / slug
        if not directory.exists():
            self.skipTest(f"generated sample not present: {slug}")
        facts = json.loads((directory / "facts.json").read_text(encoding="utf-8"))
        homepage = json.loads((directory / "00首页信息.json").read_text(encoding="utf-8"))
        modules = json.loads((directory / "00首页模块.json").read_text(encoding="utf-8"))
        validation = json.loads((directory / "validation-report.json").read_text(encoding="utf-8"))
        site_content_path = directory / "site-content.json"
        site_identity_path = directory / "site-identity.json"
        self.assertTrue(site_content_path.exists())
        self.assertTrue(site_identity_path.exists())
        site_content = json.loads(site_content_path.read_text(encoding="utf-8"))
        site_identity = json.loads(site_identity_path.read_text(encoding="utf-8"))
        self.assertEqual(facts["identity"]["placeId"], place_id)
        self.assertFalse(list(Draft202012Validator(HOMEPAGE_SCHEMA, format_checker=FormatChecker()).iter_errors(homepage)))
        self.assertFalse(list(Draft202012Validator(MODULES_SCHEMA, format_checker=FormatChecker()).iter_errors(modules)))
        self.assertFalse(list(Draft202012Validator(TEMPLATE_SITE_CONTENT_SCHEMA, format_checker=FormatChecker()).iter_errors(site_content)))
        self.assertFalse(list(Draft202012Validator(TEMPLATE_SITE_IDENTITY_SCHEMA, format_checker=FormatChecker()).iter_errors(site_identity)))
        self.assertFalse(validate_site_content(site_content, facts))
        self.assertFalse(validate_site_identity(site_identity, facts))
        bad_faq = copy.deepcopy(site_content)
        bad_faq["home"]["faq"]["items"][0]["answer"] = "One. Two. Three. Four."
        self.assertIn("TEMPLATE_FAQ_LENGTH", {error["code"] for error in validate_site_content(bad_faq, facts)})
        bad_identity = {**site_identity, "game_name": site_identity["GAME_NAME"]}
        self.assertTrue(list(Draft202012Validator(TEMPLATE_SITE_IDENTITY_SCHEMA).iter_errors(bad_identity)))
        self.assertNotEqual(validation["status"], "fail")
        self.assertEqual(len(homepage["home"]["hero"]["stats"]), 5)
        self.assertEqual(len(homepage["home"]["start"]["cards"]), 4)
        self.assertTrue((directory / "assets" / "favicon" / "favicon.ico").exists())
        self.assertEqual(len(site_content["home"]["hero"]["stats"]), 4)
        self.assertGreaterEqual(len(site_content["home"]["faq"]["items"]), 4)
        self.assertNotIn("sidebarCodes", site_content)
        self.assertNotIn("themeColor", site_content)
        self.assertNotIn("footer", site_content)
        self.assertEqual(set(site_content), {"site", "home"})
        self.assertEqual(set(site_identity), {"GAME_NAME", "OFFICIAL_GAME_URL", "DISCORD_URL", "YOUTUBE_CHANNEL_URL", "FANDOM_URL", "YOUTUBE_VIDEO_ID", "LANGUAGES"})
        self.assertEqual(site_identity["LANGUAGES"], ["en", "es", "de", "fr", "ja", "ko"])
        intake = directory / "template-intake"
        self.assertEqual(site_identity, json.loads((intake / "site-identity.json").read_text(encoding="utf-8")))
        self.assertEqual(site_content, json.loads((intake / "site-content.json").read_text(encoding="utf-8")))
        hero_files = [path for path in intake.iterdir() if path.is_file() and path.stem == "hero"]
        self.assertEqual(len(hero_files), 1)
        locale_files = {f"site-content.{locale}.json" for locale in site_identity["LANGUAGES"] if locale != "en"}
        self.assertEqual(
            {path.name for path in intake.iterdir()},
            {"site-identity.json", "site-content.json", hero_files[0].name, "favicon", *locale_files},
        )
        for locale in site_identity["LANGUAGES"]:
            if locale == "en":
                continue
            localized = json.loads((intake / f"site-content.{locale}.json").read_text(encoding="utf-8"))
            self.assertFalse(validate_localized_site_content(localized, site_content, locale, facts))
        self.assertEqual(
            {path.name for path in (intake / "favicon").iterdir()},
            {
                "favicon.ico", "favicon-16x16.png", "favicon-32x32.png", "apple-touch-icon.png",
                "android-chrome-192x192.png", "android-chrome-512x512.png", "site.webmanifest",
            },
        )
        for key in ["title", "secondaryCtaHref", "videoId"]:
            self.assertNotIn(key, site_content["home"]["hero"])
        for key in ["featured", "categories", "updates", "start", "explore"]:
            self.assertNotIn(key, site_content["home"])
        for module in modules["modules"]:
            if module["displayType"] == "code-cards":
                self.assertIn("code", module["name"].lower())
            if module["displayType"] == "tier-grid":
                self.assertTrue("tier" in module["name"].lower() or "rank" in module["name"].lower())

    def test_anime_expeditions(self):
        self._check("anime-expeditions", "84515722934860")

    def test_pursuitcore(self):
        self._check("pursuitcore", "121903154323395")
        directory = ROOT / "output" / "pursuitcore"
        if directory.exists():
            facts = json.loads((directory / "facts.json").read_text(encoding="utf-8"))
            rejected = {item["placeId"] for item in facts["identity"].get("rejectedCandidates", [])}
            self.assertIn("84498985865861", rejected)


if __name__ == "__main__":
    unittest.main()
