from __future__ import annotations

import json
import copy
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from gamewiki_automation.config import Settings
from gamewiki_automation.llm import LlmClient, _compact_schema_strings, _provider_schema, _responses_text, _web_search_calls
from gamewiki_automation.pipeline import Pipeline, _generation_evidence, _generation_facts, _module_facts, _normalize_modules, _research_facts, _select_language_codes
from gamewiki_automation.roblox import IdentityError, RobloxClient, clean_roblox_display_name, identity_match_confidence, roblox_place_id
from gamewiki_automation.steam import SteamClient, steam_app_id
from gamewiki_automation.schemas import HOMEPAGE_SCHEMA, LANGUAGE_MARKET_SCHEMA, MODULES_SCHEMA, RESEARCH_SCHEMA, TEMPLATE_SITE_CONTENT_SCHEMA, TEMPLATE_SITE_IDENTITY_SCHEMA
from gamewiki_automation.template_contract import build_site_content, build_site_identity, export_existing_output, validate_localized_site_content, validate_template_contract
from gamewiki_automation.util import clean_json_text, dump_json, normalized_name, public_game_name, slugify
from gamewiki_automation.validate import _cost_summary


class FakeResponse:
    status_code = 200
    text = """
    [Anime Expeditions](https://www.roblox.com/games/84515722934860/Anime-Expeditions?placeId=84515722934860&position=0&universeId=7613921865)
    [Other Anime](https://www.roblox.com/games/123/Other-Anime?placeId=123&position=1&universeId=456)
    """


class FakeHttp:
    def get(self, *_args, **_kwargs):
        return FakeResponse()

    def get_json(self, url, **_kwargs):
        if "universeIds=" in url:
            return {"data": [
                {"id": 7613921865, "name": "Anime Expeditions [UPDATE]", "description": "tower defense", "visits": 100, "creator": {"name": "Studio"}},
                {"id": 456, "name": "Other Anime", "description": "other", "visits": 10, "creator": {"name": "Other"}},
            ]}
        raise AssertionError(url)


class FakeToApisHttp:
    def __init__(self):
        self.payload = None

    def post_json(self, _url, payload, _headers, **_kwargs):
        self.payload = payload
        return {
            "id": "resp_test",
            "status": "completed",
            "model": "gpt-5.3-codex",
            "output": [
                {"type": "reasoning"},
                {"type": "web_search_call"},
                {"type": "message", "content": [{"type": "output_text", "text": '{"ok":true}'}]},
            ],
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        }


class FakeSteamHttp:
    def get_json(self, url, **_kwargs):
        if "appdetails" in url:
            return {"3712080": {"success": True, "data": {
                "name": "Funnel Runners",
                "short_description": "Survive escalating tornadoes with up to 7 friends.",
                "about_the_game": "<p>Repair your van and escape.</p>",
                "developers": ["Supernova Studios LLC"],
                "publishers": ["Supernova Publishing"],
                "genres": [{"description": "Early Access"}, {"description": "Action"}],
                "categories": [{"description": "Online Co-op"}],
                "price_overview": {"final": 1349, "currency": "USD", "final_formatted": "$13.49"},
                "release_date": {"coming_soon": False, "date": "Jul 16, 2026"},
                "platforms": {"windows": True, "mac": False, "linux": False},
                "controller_support": "full",
                "header_image": "https://cdn.example/header.jpg",
                "screenshots": [{"path_full": "https://cdn.example/screenshot.jpg"}],
                "movies": [],
            }}}
        if "appreviews" in url:
            return {"query_summary": {
                "total_reviews": 100, "total_positive": 84,
                "review_score_desc": "Very Positive",
            }}
        raise AssertionError(url)


class CoreTests(unittest.TestCase):
    def test_public_game_name_removes_only_leading_bracketed_cjk_alias(self) -> None:
        self.assertEqual(public_game_name({"canonicalName": "(学乱) Gakuran"}), "Gakuran")
        self.assertEqual(public_game_name({"canonicalName": "【学乱】 Gakuran"}), "Gakuran")
        self.assertEqual(public_game_name({"canonicalName": "学園アイドルマスター"}), "学園アイドルマスター")
        self.assertEqual(public_game_name({"canonicalName": "Gakuran 学乱"}), "Gakuran 学乱")

    def test_generation_facts_separates_public_and_official_platform_names(self) -> None:
        facts = {"identity": {"canonicalName": "(学乱) Gakuran", "canonicalUrl": "https://example.com"}}
        generated = _generation_facts(facts)
        self.assertEqual(generated["identity"]["canonicalName"], "Gakuran")
        self.assertEqual(generated["identity"]["officialPlatformName"], "(学乱) Gakuran")
        self.assertEqual(facts["identity"]["canonicalName"], "(学乱) Gakuran")

    def test_site_content_uses_public_name_but_preserves_official_developer(self) -> None:
        facts = {
            "identity": {"canonicalName": "(学乱) Gakuran", "platform": "Roblox"},
            "developer": {"name": "(学乱) Gakuran"},
            "game": {},
        }
        homepage = {
            "metadata": {
                "title": "(学乱) Gakuran Wiki",
                "description": "Learn (学乱) Gakuran with practical beginner information.",
            },
            "home": {
                "hero": {},
                "aboutGame": {"paragraphs": ["(学乱) Gakuran is a Roblox game."]},
                "finalCta": {},
            },
        }
        content = build_site_content(facts, homepage)
        self.assertEqual(content["home"]["meta"]["title"], "Gakuran Wiki")
        self.assertEqual(content["home"]["aboutGame"]["paragraphs"], ["Gakuran is a Roblox game."])
        self.assertEqual(content["site"]["developer"], "(学乱) Gakuran")

    def test_research_merge_preserves_rejected_identity_candidates(self):
        pipeline = Pipeline.__new__(Pipeline)
        pipeline.http = FakeHttp()
        facts = {
            "identity": {
                "placeId": "121903154323395",
                "rejectedCandidates": [{"placeId": "84498985865861", "reason": "name collision"}],
            },
            "officialLinks": {},
        }
        research = {
            "officialLinks": {}, "trailer": "", "codes": [], "gameplayFacts": [],
            "languageSignals": [], "notes": [],
        }
        merged, _ = pipeline._merge_research(facts, {"sources": [], "claims": []}, research)
        self.assertEqual(
            [item["placeId"] for item in merged["identity"]["rejectedCandidates"]],
            ["84498985865861"],
        )

    def test_slug_and_name_normalization(self):
        self.assertEqual(slugify("PURSUITCORE [Update!]"), "pursuitcore-update")
        self.assertEqual(normalized_name("Anime Expeditions [TIME CHAMBER]"), "animeexpeditions")

    def test_json_fence_cleanup(self):
        self.assertEqual(clean_json_text("```json\n{\"ok\": true}\n```"), {"ok": True})

    def test_discover_selects_exact_name(self):
        selected, candidates = RobloxClient(FakeHttp()).select_identity("Anime Expeditions")
        self.assertEqual(selected["placeId"], "84515722934860")
        self.assertGreaterEqual(selected["matchScore"], 0.9)
        self.assertEqual(len(candidates), 2)

    def test_roblox_official_url_bypasses_ambiguous_discover_results(self):
        class OfficialUrlHttp(FakeHttp):
            def get_json(self, url, **_kwargs):
                if "universes/v1/places/84515722934860" in url:
                    return {"universeId": 7613921865}
                return super().get_json(url, **_kwargs)

        url = "https://www.roblox.com/games/84515722934860/Anime-Expeditions"
        self.assertEqual(roblox_place_id(url), "84515722934860")
        selected, candidates = RobloxClient(OfficialUrlHttp()).select_identity("Anime Expeditions", url)
        self.assertEqual(selected["placeId"], "84515722934860")
        self.assertEqual(candidates[0]["source"], "explicit-official-url")

    def test_roblox_official_url_allows_disambiguated_search_label(self):
        class AnomalyHttp(FakeHttp):
            def get_json(self, url, **_kwargs):
                if "universes/v1/places/78515283254292" in url:
                    return {"universeId": 7613921865}
                if "universeIds=" in url:
                    return {"data": [{
                        "id": 7613921865,
                        "name": "Animal Hospital (Anomaly) 🧪",
                        "description": "official game",
                        "visits": 100,
                        "creator": {"name": "Animal Anomaly"},
                    }]}
                raise AssertionError(url)

        url = "https://www.roblox.com/games/78515283254292/Animal-Hospital"
        selected, candidates = RobloxClient(AnomalyHttp()).select_identity(
            "Animal Hospital Anomaly", url
        )

        self.assertEqual(selected["placeId"], "78515283254292")
        self.assertEqual(selected["identitySelection"], "explicit-place-id")
        self.assertLess(selected["matchScore"], 0.72)
        self.assertEqual(identity_match_confidence(selected), 1.0)
        self.assertEqual(len(candidates), 1)

    def test_name_selected_identity_preserves_semantic_confidence(self):
        self.assertEqual(
            identity_match_confidence({"matchScore": 0.91, "identitySelection": "name-confidence"}),
            0.91,
        )

    def test_clean_roblox_name_keeps_disambiguator_but_drops_emoji(self):
        self.assertEqual(
            clean_roblox_display_name("Animal Hospital (Anomaly) 🧪"),
            "Animal Hospital (Anomaly)",
        )

    def test_identity_rejects_character_similar_but_different_noun(self):
        class SimilarWrongHttp(FakeHttp):
            def get_json(self, url, **_kwargs):
                if "universeIds=" in url:
                    return {"data": [
                        {"id": 7613921865, "name": "Build a Bunker", "description": "wrong game", "visits": 100, "creator": {"name": "Studio"}},
                        {"id": 456, "name": "Build a Bunker!", "description": "also wrong", "visits": 10, "creator": {"name": "Other"}},
                    ]}
                raise AssertionError(url)

        with self.assertRaises(IdentityError) as caught:
            RobloxClient(SimilarWrongHttp()).select_identity("Build a Bucket")
        self.assertEqual(len(caught.exception.candidates), 2)
        self.assertLess(caught.exception.candidates[0]["tokenCoverage"], 1.0)

    def test_steam_official_url_selects_and_normalizes_platform_facts(self):
        url = "https://store.steampowered.com/app/3712080/Funnel_Runners/"
        self.assertEqual(steam_app_id(url), "3712080")
        client = SteamClient(FakeSteamHttp())
        selected, candidates = client.select_identity("Funnel Runners", url)
        facts, evidence, raw = client.collect("Funnel Runners", selected)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(facts["identity"]["platform"], "Steam")
        self.assertEqual(facts["identity"]["appId"], "3712080")
        self.assertEqual(facts["game"]["maxPlayers"], 8)
        self.assertEqual(facts["game"]["price"], 13.49)
        self.assertEqual(facts["publisher"]["name"], "Supernova Publishing")
        self.assertEqual(facts["dynamicStats"]["approvalPercent"], 84.0)
        self.assertEqual(evidence["sources"][0]["publisher"], "Steam")
        self.assertEqual(raw["appDetails"]["controller_support"], "full")

    def test_site_identity_only_labels_verified_youtube_channel_urls(self):
        facts = {
            "identity": {"canonicalName": "Test Game", "canonicalUrl": "https://example.com"},
            "officialLinks": {"youtube": "https://www.youtube.com/watch?v=abcdefghijk"},
        }
        self.assertEqual(build_site_identity(facts)["YOUTUBE_CHANNEL_URL"], "")
        facts["officialLinks"]["youtube"] = "https://www.youtube.com/@VerifiedStudio"
        self.assertEqual(
            build_site_identity(facts)["YOUTUBE_CHANNEL_URL"],
            "https://www.youtube.com/@VerifiedStudio",
        )

    def test_steam_official_url_allows_shortened_search_label(self):
        class LongTitleSteamHttp(FakeSteamHttp):
            def get_json(self, url, **kwargs):
                if "appdetails" in url:
                    payload = super().get_json(url.replace("3950130", "3712080"), **kwargs)
                    details = payload["3712080"]["data"]
                    details["name"] = "Database Detective: Minor Crimes Division"
                    return {"3950130": {"success": True, "data": details}}
                return super().get_json(url, **kwargs)

        url = "https://store.steampowered.com/app/3950130/Database_Detective_Minor_Crimes_Division/"
        client = SteamClient(LongTitleSteamHttp())
        selected, candidates = client.select_identity("Database Detective", url)
        facts, _, _ = client.collect("Database Detective", selected)

        self.assertEqual(selected["appId"], "3950130")
        self.assertEqual(selected["identitySelection"], "explicit-app-id")
        self.assertEqual(selected["matchScore"], 0.0)
        self.assertEqual(facts["identity"]["matchConfidence"], 1.0)
        self.assertEqual(len(candidates), 1)

    def test_provider_schema_removes_format_without_mutating_local_schema(self):
        compatible = _provider_schema(HOMEPAGE_SCHEMA)
        serialized = json.dumps(compatible)
        self.assertNotIn('"format"', serialized)
        self.assertIn('"format"', json.dumps(HOMEPAGE_SCHEMA))

    def test_schema_string_compaction_repairs_only_overlong_localized_values(self):
        schema = {
            "type": "object",
            "properties": {
                "description": {"type": "string", "minLength": 10, "maxLength": 30},
                "label": {"type": "string", "maxLength": 20},
            },
        }
        source = {
            "description": "Eine ausführliche lokalisierte Beschreibung mit zu vielen Zeichen.",
            "label": "Unchanged",
        }
        compacted = _compact_schema_strings(source, schema)
        self.assertLessEqual(len(compacted["description"]), 30)
        self.assertTrue(compacted["description"].endswith("…"))
        self.assertEqual(compacted["label"], "Unchanged")

    def test_toapis_responses_mixed_output_and_web_tool(self):
        response = {"output": [{"type": "reasoning"}, {"type": "web_search_call"}, {"type": "message", "content": [{"type": "output_text", "text": "answer"}]}]}
        self.assertEqual(_responses_text(response), "answer")
        self.assertEqual(_web_search_calls(response), 1)

        settings = Settings(
            toapis_api_key="test-key", perplexity_api_key=None,
            toapis_model="gpt-5.3-codex-official", toapis_web_model="gpt-5.3-codex-official",
            toapis_reasoning_effort="low", perplexity_model="sonar-pro",
            output_dir=Path("output"), cache_dir=Path(".cache"), request_timeout=30,
        )
        http = FakeToApisHttp()
        data, meta = LlmClient(settings, http)._toapis(
            "test", "Return JSON.", "Find the official URL.",
            {"type": "object", "additionalProperties": False, "required": ["ok"], "properties": {"ok": {"type": "boolean"}}},
            web=True,
        )
        self.assertEqual(data, {"ok": True})
        self.assertEqual(meta["provider"], "toapis")
        self.assertEqual(meta["webSearchCalls"], 1)
        self.assertEqual(http.payload["tools"], [{"type": "web_search_preview"}])
        self.assertEqual(http.payload["tool_choice"], "required")

    def test_unknown_provider_cost_is_not_reported_as_zero(self):
        summary = _cost_summary([
            {"task": "research", "cached": False, "costUsd": 0.03},
            {"task": "homepage", "cached": False, "costUsd": None},
        ])
        self.assertIsNone(summary["totalUsd"])
        self.assertEqual(summary["knownUsd"], 0.03)
        self.assertFalse(summary["complete"])
        self.assertEqual(summary["missingCostTasks"], ["homepage"])

    def test_all_schemas_are_valid(self):
        for schema in (RESEARCH_SCHEMA, LANGUAGE_MARKET_SCHEMA, HOMEPAGE_SCHEMA, MODULES_SCHEMA, TEMPLATE_SITE_IDENTITY_SCHEMA, TEMPLATE_SITE_CONTENT_SCHEMA):
            Draft202012Validator.check_schema(schema)

    def test_language_selection_is_fixed_product_policy(self):
        candidates = [
            {"code": "en", "recommendation": "include", "confidence": 0.99, "officialSupport": True, "sourceUrls": ["https://example.com/en"], "signals": [{"publisher": "Official"}]},
            {"code": "es", "recommendation": "include", "confidence": 0.8, "officialSupport": False, "sourceUrls": ["https://youtube.com/watch?v=1", "https://youtube.com/watch?v=2"], "signals": [{"publisher": "Creator A"}, {"publisher": "Creator B"}]},
            {"code": "pt", "recommendation": "include", "confidence": 0.9, "officialSupport": False, "sourceUrls": ["https://example.com/pt"], "signals": [{"publisher": "Only One"}]},
            {"code": "vi", "recommendation": "include", "confidence": 0.88, "officialSupport": False, "sourceUrls": ["https://youtube.com/watch?v=one"], "signals": [{"publisher": "Label A"}, {"publisher": "Label B"}]},
            {"code": "ja", "recommendation": "include", "confidence": 0.85, "officialSupport": True, "sourceUrls": ["https://official.example/ja"], "signals": [{"signalType": "official-localization", "publisher": "Game Studio", "sourceUrls": ["https://official.example/ja"]}]},
        ]
        expected = ["en", "es", "de", "fr", "ja"]
        self.assertEqual(_select_language_codes([]), expected)
        self.assertEqual(_select_language_codes(candidates), expected)

    def test_template_contract_rejects_legacy_or_extra_fields(self):
        invalid = {"themeColor": {}, "site": {}, "home": {}, "sidebarCodes": []}
        errors = list(Draft202012Validator(TEMPLATE_SITE_CONTENT_SCHEMA).iter_errors(invalid))
        self.assertTrue(errors)

    def test_identity_languages_require_unique_lowercase_iso_codes(self):
        base = {"GAME_NAME": "Test Game", "OFFICIAL_GAME_URL": "https://www.roblox.com/games/1/test"}
        self.assertFalse(list(Draft202012Validator(TEMPLATE_SITE_IDENTITY_SCHEMA).iter_errors({**base, "LANGUAGES": ["en", "es"]})))
        self.assertTrue(list(Draft202012Validator(TEMPLATE_SITE_IDENTITY_SCHEMA).iter_errors({**base, "LANGUAGES": ["EN"]})))
        self.assertTrue(list(Draft202012Validator(TEMPLATE_SITE_IDENTITY_SCHEMA).iter_errors({**base, "LANGUAGES": ["en", "en"]})))
        self.assertTrue(list(Draft202012Validator(TEMPLATE_SITE_IDENTITY_SCHEMA).iter_errors({**base, "LANGUAGES": ["zz"]})))

    def test_template_schema_matches_current_extra_sections_contract(self):
        home_properties = TEMPLATE_SITE_CONTENT_SCHEMA["properties"]["home"]["properties"]
        self.assertIn("extraSections", home_properties)
        self.assertEqual(TEMPLATE_SITE_CONTENT_SCHEMA["$defs"]["extraSection"]["properties"]["items"]["minItems"], 4)
        self.assertNotIn("category", TEMPLATE_SITE_CONTENT_SCHEMA["$defs"]["tool"]["required"])

    def test_localized_content_requires_exact_structure_and_immutable_routes(self):
        facts = {"identity": {"canonicalName": "Test Game"}}
        english = {
            "site": {
                "tagline": "Fan-Made Wiki",
                "description": "A complete fan-made Test Game wiki with beginner information, current codes, gameplay facts, and useful answers.",
                "gamePlatform": ["Roblox"],
            },
            "home": {
                "meta": {
                    "title": "Test Game Wiki and Beginner Guide",
                    "description": "Explore the complete Test Game wiki for beginner information, current codes, gameplay facts, and useful answers.",
                },
                "hero": {
                    "eyebrow": "Fan-Made Guide",
                    "description": "Learn the core Test Game experience before joining your first Roblox server.",
                    "stats": [{"value": "Roblox", "label": "Platform"}],
                },
                "aboutGame": {
                    "title": "What is Test Game?",
                    "paragraphs": [
                        "Test Game is a Roblox experience created for players who enjoy learning together.",
                        "This homepage collects reliable facts and practical starting information for new players.",
                    ],
                    "stats": [{"label": "Developer", "value": "Test Studio"}],
                },
                "liveTools": {
                    "title": "Active Codes",
                    "items": [{"title": "FREE", "description": "Claim a free reward.", "href": "/codes", "category": "codes"}],
                },
                "faq": {"title": "Frequently Asked Questions", "items": [
                    {"question": "What is Test Game?", "answer": "Test Game is a Roblox experience for online players."},
                    {"question": "Who made Test Game?", "answer": "Test Game was created by Test Studio for Roblox players."},
                    {"question": "Where is Test Game available?", "answer": "You can play Test Game through its official Roblox experience page."},
                    {"question": "Is Test Game free to play?", "answer": "Test Game is available to join through the Roblox platform."},
                ]},
                "finalCta": {"title": "Play Test Game", "description": "Open the official Roblox experience and start playing Test Game today."},
            },
        }
        spanish = copy.deepcopy(english)
        def localize(value, path=""):
            if isinstance(value, dict):
                return {key: localize(child, f"{path}.{key}".strip(".")) for key, child in value.items()}
            if isinstance(value, list):
                return [localize(child, f"{path}.{index}".strip(".")) for index, child in enumerate(value)]
            if not isinstance(value, str):
                return value
            key = path.rsplit(".", 1)[-1]
            immutable = key in {"href", "category"} or key.endswith("Href") or value in {"Roblox", "FREE", "Test Studio"}
            return value if immutable else "ES: " + value
        spanish = localize(spanish)
        self.assertFalse(validate_localized_site_content(spanish, english, "es", facts))

        bad_route = copy.deepcopy(spanish)
        bad_route["home"]["liveTools"]["items"][0]["href"] = "/codigos"
        self.assertIn("TEMPLATE_LOCALE_IMMUTABLE_MISMATCH", {e["code"] for e in validate_localized_site_content(bad_route, english, "es", facts)})

        missing = copy.deepcopy(spanish)
        del missing["home"]["faq"]
        self.assertIn("TEMPLATE_LOCALE_STRUCTURE", {e["code"] for e in validate_localized_site_content(missing, english, "es", facts)})

        self.assertIn("TEMPLATE_LOCALE_NOT_TRANSLATED", {e["code"] for e in validate_localized_site_content(english, english, "es", facts)})

    def test_declared_non_english_locale_file_is_required(self):
        facts = {
            "identity": {"canonicalName": "Test Game", "canonicalUrl": "https://www.roblox.com/games/1/test-game"},
            "officialLinks": {}, "game": {}, "developer": {}, "dynamicStats": {}, "codes": [], "gameplayFacts": [],
            "languages": ["en", "es"],
        }
        identity = {
            "GAME_NAME": "Test Game", "OFFICIAL_GAME_URL": "https://www.roblox.com/games/1/test-game",
            "DISCORD_URL": "", "YOUTUBE_CHANNEL_URL": "", "FANDOM_URL": "", "YOUTUBE_VIDEO_ID": "",
            "LANGUAGES": ["en", "es"],
        }
        report = validate_template_contract(identity, {"site": {}, "home": {}}, facts)
        self.assertIn("TEMPLATE_LOCALE_MISSING", {error["code"] for error in report["errors"]})

    def test_sourced_claimed_active_codes_enter_live_tools_with_disclosure(self):
        facts = {
            "identity": {"canonicalName": "Test Game"},
            "game": {}, "developer": {}, "dynamicStats": {}, "gameplayFacts": [],
            "codes": [
                {"code": "COMMUNITY", "reward": "Ten rerolls.", "status": "claimed-active", "officiallyVerified": False, "sourceUrls": ["https://example.com/codes"]},
                {"code": "NO-SOURCE", "reward": "One gem.", "status": "claimed-active", "officiallyVerified": False, "sourceUrls": []},
                {"code": "UNKNOWN", "reward": "Unknown.", "status": "unknown", "officiallyVerified": False, "sourceUrls": ["https://example.com/unknown"]},
            ],
        }
        content = build_site_content(facts, {"metadata": {}, "home": {}})
        items = content["home"]["liveTools"]["items"]
        self.assertEqual([item["title"] for item in items], ["COMMUNITY"])
        self.assertIn("Community-reported active", items[0]["description"])

    def test_failed_template_export_removes_ready_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            facts = {
                "identity": {"canonicalName": "Test Game"},
                "developer": {"name": "Test Studio"},
                "game": {"createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-02T00:00:00Z", "maxPlayers": 8, "officialDescription": "tower defense"},
                "dynamicStats": {"visits": 100}, "codes": [], "gameplayFacts": [],
            }
            homepage = {
                "metadata": {"description": "A" * 100},
                "theme": {"light": {}, "dark": {}},
                "home": {
                    "meta": {"title": "Test Game Wiki", "description": "B" * 100},
                    "hero": {"eyebrow": "Fan Guide", "description": "C" * 50},
                    "aboutGame": {"title": "What is Test Game?", "paragraphs": ["D" * 40, "E" * 40]},
                    "finalCta": {"title": "Play Test Game", "description": "F" * 30},
                },
            }
            dump_json(directory / "facts.json", facts)
            dump_json(directory / "00首页信息.json", homepage)
            dump_json(directory / "site-content.json", {"stale": True})
            dump_json(directory / "site-identity.json", {"stale": True})
            dump_json(directory / "template-intake" / "site-content.json", {"stale": True})
            report = export_existing_output(directory)
            self.assertEqual(report["status"], "fail")
            self.assertIn("TEMPLATE_ASSET_MISSING", {error["code"] for error in report["errors"]})
            self.assertFalse((directory / "site-content.json").exists())
            self.assertFalse((directory / "site-identity.json").exists())
            self.assertFalse((directory / "template-intake").exists())
            self.assertTrue((directory / "raw" / "site-content.invalid.json").exists())
            self.assertTrue((directory / "raw" / "site-identity.invalid.json").exists())

    def test_module_display_type_normalization(self):
        source = {"modules": [
            {"name": "PURSUITCORE Roles", "displayType": "code-cards"},
            {"name": "PURSUITCORE Popularity", "displayType": "tier-grid"},
            {"name": "PURSUITCORE Codes", "displayType": "code-cards"},
        ]}
        normalized, changes = _normalize_modules(source)
        self.assertEqual([m["displayType"] for m in normalized["modules"]], ["card-list", "card-list", "code-cards"])
        self.assertEqual(len(changes), 2)

    def test_audit_fields_do_not_enter_generation_context(self):
        source = {"identity": {"placeId": "1", "rejectedCandidates": [{"placeId": "2"}]}, "researchNotes": ["audit"], "dynamicStats": {"retrievedAt": "now", "visits": 2}}
        filtered = _generation_facts(source)
        self.assertNotIn("rejectedCandidates", filtered["identity"])
        self.assertNotIn("researchNotes", filtered)
        self.assertIn("rejectedCandidates", source["identity"])
        self.assertNotIn("retrievedAt", filtered["dynamicStats"])

    def test_research_context_excludes_volatile_stats(self):
        source = {"identity": {"placeId": "1"}, "developer": {}, "game": {}, "officialLinks": {"roblox": "https://example.com", "robloxGroup": None}, "dynamicStats": {"playing": 99}, "media": {"icon": "x"}}
        filtered = _research_facts(source)
        self.assertNotIn("dynamicStats", filtered)
        self.assertNotIn("media", filtered)

    def test_generation_evidence_excludes_timestamps(self):
        source = {"sources": [{"id": "s", "retrievedAt": "now"}], "claims": []}
        self.assertNotIn("retrievedAt", _generation_evidence(source)["sources"][0])

    def test_module_context_excludes_dynamic_values(self):
        source = {"identity": {}, "dynamicStats": {"playing": 3}, "media": {"icon": "x"}}
        filtered = _module_facts(source)
        self.assertNotIn("dynamicStats", filtered)
        self.assertNotIn("media", filtered)


if __name__ == "__main__":
    unittest.main()
