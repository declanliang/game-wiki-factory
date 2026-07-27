from __future__ import annotations

import unittest
import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from get_search.classifier import Candidate
from get_search.llm_cluster import (
    LLMCall,
    _responses_text_and_annotations,
    _request_toapis,
    apply_cluster_decisions,
    cluster_candidates,
    supplement_context_opportunities,
)


class LLMClusterTests(unittest.TestCase):
    def test_toapis_request_retries_transient_ssl_url_error(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b'{"ok": true}'

        with patch("get_search.llm_cluster.time.sleep"), patch(
            "get_search.llm_cluster.urllib.request.urlopen",
            side_effect=[urllib.error.URLError("SSL EOF"), Response()],
        ) as urlopen:
            result = _request_toapis("secret", "https://example.invalid", {"x": 1})

        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 2)

    def test_cluster_batches_every_candidate_and_reuses_checkpoints(self) -> None:
        candidates = [
            self.candidate(f"hellhole topic {index}", {"autocomplete"}, 100 - index)
            for index in range(5)
        ]
        calls: list[list[str]] = []

        def fake_batch(api_key, topic, batch, game_context, model):
            keywords = [item.keyword for item in batch]
            calls.append(keywords)
            return LLMCall(
                model=model,
                data={
                    "topic_name": topic,
                    "decisions": [self.decision(keyword) for keyword in keywords],
                    "category_purposes": [{"category": "guide", "purpose": "Guides"}],
                    "notes": [],
                },
                usage={"total_tokens": len(keywords)},
                cost_usd=None,
                response_meta={"model": model},
            )

        with TemporaryDirectory() as temporary, patch(
            "get_search.llm_cluster._cluster_candidate_batch", side_effect=fake_batch
        ):
            checkpoint_dir = Path(temporary)
            first = cluster_candidates(
                "key", "Hellhole", candidates, {}, batch_size=2, checkpoint_dir=checkpoint_dir
            )
            second = cluster_candidates(
                "key", "Hellhole", candidates, {}, batch_size=2, checkpoint_dir=checkpoint_dir
            )

        self.assertEqual([len(batch) for batch in calls], [2, 2, 1])
        self.assertEqual(len(first.data["decisions"]), 5)
        self.assertEqual(first.usage["total_tokens"], 5)
        self.assertEqual(second.data, first.data)
        self.assertEqual(len(calls), 3, "the second call must be fully checkpointed")

    def test_cluster_checkpoint_is_invalidated_when_trusted_context_changes(self) -> None:
        candidates = [self.candidate("hellhole roblox upgrades", {"youtube"})]
        calls = 0

        def fake_batch(api_key, topic, batch, game_context, model):
            nonlocal calls
            calls += 1
            return LLMCall(
                model=model,
                data={
                    "topic_name": topic,
                    "decisions": [self.decision(batch[0].keyword, category="upgrades")],
                    "category_purposes": [],
                    "notes": [],
                },
                usage={"total_tokens": 1},
                cost_usd=None,
                response_meta={"model": model},
            )

        with TemporaryDirectory() as temporary, patch(
            "get_search.llm_cluster._cluster_candidate_batch", side_effect=fake_batch
        ):
            checkpoint_dir = Path(temporary)
            cluster_candidates(
                "key", "Hellhole Roblox", candidates,
                {"trusted_basic_info": {"description": "loot"}},
                checkpoint_dir=checkpoint_dir,
            )
            cluster_candidates(
                "key", "Hellhole Roblox", candidates,
                {"trusted_basic_info": {"description": "loot"}},
                checkpoint_dir=checkpoint_dir,
            )
            cluster_candidates(
                "key", "Hellhole Roblox", candidates,
                {"trusted_basic_info": {"description": "loot and upgrades"}},
                checkpoint_dir=checkpoint_dir,
            )

        self.assertEqual(calls, 2)

    def candidate(self, keyword: str, sources: set[str], score: float = 10) -> Candidate:
        item = Candidate(keyword=keyword, sources=sources)
        item.score = score
        return item

    def decision(
        self,
        keyword: str,
        action: str = "keep",
        category: str | None = "guide",
        confidence: float = 0.9,
    ) -> dict[str, object]:
        return {
            "keyword": keyword,
            "action": action,
            "category": category,
            "merge_into": None,
            "entity_type": "guide",
            "confidence": confidence,
            "reason": "test decision",
        }

    def test_hard_filters_override_llm_keep_but_allow_youtube_only(self) -> None:
        candidates = [
            self.candidate("anime expeditions beginner guide", {"autocomplete"}, 50),
            self.candidate("anime expeditions discord", {"autocomplete"}, 40),
            self.candidate("anime expeditions tier list", {"youtube"}, 30),
            self.candidate("anime expeditions release date", {"trends"}, 20),
        ]
        data = {
            "decisions": [
                self.decision("anime expeditions beginner guide"),
                self.decision("anime expeditions discord", category="servers"),
                self.decision("anime expeditions tier list", category="tier list"),
                self.decision("anime expeditions release date", category="updates", confidence=0.4),
            ]
        }
        selected, rejected, errors = apply_cluster_decisions(
            "Anime Expeditions", candidates, data
        )
        self.assertEqual(
            [item.keyword for item in selected],
            ["anime expeditions beginner guide", "anime expeditions tier list"],
        )
        reasons = {item["keyword"]: item["reason"] for item in rejected}
        self.assertIn("forbidden standalone", reasons["anime expeditions discord"])
        self.assertIn("below", reasons["anime expeditions release date"])
        self.assertEqual(errors, [])

    def test_missing_decisions_are_dropped_without_invalidating_the_plan(self) -> None:
        candidates = [self.candidate("anime expeditions units", {"labs"})]
        data = {"decisions": [self.decision("anime expeditions made up keyword")]}
        selected, rejected, errors = apply_cluster_decisions(
            "Anime Expeditions", candidates, data
        )
        self.assertEqual(selected, [])
        self.assertEqual(rejected[0]["reason"], "LLM omitted candidate")
        self.assertEqual(len(errors), 1)
        self.assertTrue(any("unknown keyword" in error for error in errors))

    def test_identical_duplicate_decision_keeps_one_without_failing_run(self) -> None:
        candidates = [
            self.candidate("fallout new vegas steam how to get full screen", {"autocomplete"})
        ]
        first = self.decision(
            "fallout new vegas steam how to get full screen",
            category="guide",
            confidence=0.82,
        )
        second = dict(first)
        second["confidence"] = 0.91
        selected, rejected, errors = apply_cluster_decisions(
            "Fallout New Vegas Steam",
            candidates,
            {"decisions": [first, second]},
        )
        self.assertEqual(
            [item.keyword for item in selected],
            ["fallout new vegas steam how to get full screen"],
        )
        self.assertEqual(rejected, [])
        self.assertEqual(errors, [])

    def test_conflicting_duplicate_decision_drops_only_that_keyword(self) -> None:
        candidates = [
            self.candidate("fallout new vegas steam full screen", {"autocomplete"}),
            self.candidate("fallout new vegas steam companions", {"autocomplete"}),
        ]
        selected, rejected, errors = apply_cluster_decisions(
            "Fallout New Vegas Steam",
            candidates,
            {
                "decisions": [
                    self.decision("fallout new vegas steam full screen", category="guide"),
                    self.decision(
                        "fallout new vegas steam full screen",
                        action="drop",
                        category=None,
                    ),
                    self.decision("fallout new vegas steam companions", category="characters"),
                ]
            },
        )
        self.assertEqual(
            [item.keyword for item in selected],
            ["fallout new vegas steam companions"],
        )
        reasons = {item["keyword"]: item["reason"] for item in rejected}
        self.assertIn("conflicting duplicate", reasons["fallout new vegas steam full screen"])
        self.assertEqual(errors, [])

    def test_context_opportunities_require_strong_evidence_and_profile_category(self) -> None:
        context = {
            "trusted_basic_info": {
                "game_profile": {
                    "categoryCandidates": [{"id": "characters"}, {"id": "tier-list"}]
                }
            },
            "page_opportunities": [
                {
                    "topic_suffix": "akaza unit",
                    "page_type": "entity",
                    "category": "characters",
                    "entity_name": "Akaza",
                    "entity_type": "unit",
                    "player_intent": "How to obtain and use Akaza",
                    "confidence": 0.9,
                    "evidence_urls": ["https://example.com/official-akaza"],
                    "evidence_types": ["official"],
                    "official_or_creator": True,
                },
                {
                    "topic_suffix": "rumored unit",
                    "page_type": "entity",
                    "category": "characters",
                    "entity_name": "Rumor",
                    "entity_type": "unit",
                    "player_intent": "Find the rumored unit",
                    "confidence": 0.8,
                    "evidence_urls": ["https://example.com/one"],
                    "evidence_types": ["community"],
                    "official_or_creator": False,
                },
                {
                    "topic_suffix": "map route",
                    "page_type": "guide",
                    "category": "floors",
                    "entity_name": None,
                    "entity_type": None,
                    "player_intent": "Find the map route",
                    "confidence": 0.95,
                    "evidence_urls": ["https://example.com/official-map"],
                    "evidence_types": ["official"],
                    "official_or_creator": True,
                },
            ],
        }
        selected, rejected = supplement_context_opportunities("Anime Squadron Roblox", [], context)
        self.assertEqual([item.keyword for item in selected], ["anime squadron roblox akaza unit"])
        self.assertEqual(selected[0].page_type, "entity")
        self.assertEqual(selected[0].entity_name, "Akaza")
        reasons = [item["reason"] for item in rejected]
        self.assertTrue(any("two distinct URLs" in reason for reason in reasons))
        self.assertTrue(any("outside the Basic Info profile" in reason for reason in reasons))

    def test_no_category_minimum_is_enforced(self) -> None:
        candidates = [self.candidate("anime expeditions traits", {"autocomplete"})]
        data = {"decisions": [self.decision("anime expeditions traits", category="traits")]}
        selected, rejected, errors = apply_cluster_decisions(
            "Anime Expeditions", candidates, data
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].category, "traits")
        self.assertEqual(rejected, [])
        self.assertEqual(errors, [])

    def test_responses_output_records_web_search_and_text(self) -> None:
        raw = {
            "output": [
                {"type": "web_search_call", "status": "completed"},
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"topic":"anime expeditions"}',
                            "annotations": [{"type": "url_citation", "url": "https://roblox.com"}],
                        }
                    ],
                },
            ]
        }
        text, annotations, output_types = _responses_text_and_annotations(raw)
        self.assertEqual(text, '{"topic":"anime expeditions"}')
        self.assertEqual(annotations[0]["url"], "https://roblox.com")
        self.assertEqual(output_types, ["web_search_call", "message"])


if __name__ == "__main__":
    unittest.main()
