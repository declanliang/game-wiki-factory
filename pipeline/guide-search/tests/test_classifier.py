import unittest

from get_search.classifier import (
    Candidate,
    build_keywords_json,
    classify,
    extract_candidates,
    normalize_keyword,
    select_keywords,
    validate_keywords,
)


def response_with_result(result):
    return {
        "status_code": 20000,
        "cost": 0.01,
        "tasks": [{"status_code": 20000, "result": [result]}],
    }


class ClassifierTests(unittest.TestCase):
    def test_validation_allows_no_guide_when_evidence_is_sparse(self) -> None:
        data = {
            "topic_name": "anime paradox x",
            "categories": [
                {"category": "codes", "keywords": ["anime paradox x codes"]},
                {"category": "tier list", "keywords": ["anime paradox x tier list"]},
            ],
        }
        self.assertEqual(validate_keywords(data), [])

    def test_normalize_and_risk_filter(self):
        topic = "animal hospital roblox"
        self.assertEqual(
            normalize_keyword("Animal Hospital Roblox Codes", topic),
            "animal hospital roblox codes",
        )
        self.assertIsNone(normalize_keyword("animal hospital roblox script", topic))
        self.assertIsNone(normalize_keyword("animal hospital roblox macro", topic))
        self.assertIsNone(normalize_keyword("animal hospital roblox", topic))
        self.assertEqual(
            normalize_keyword("animal hospital anomaly roblox", topic),
            "animal hospital roblox anomaly",
        )
        self.assertIsNone(normalize_keyword("where is the animal hospital in greenville roblox", topic))
        self.assertEqual(
            normalize_keyword("beginner guide", topic, allow_unprefixed=True),
            "animal hospital roblox beginner guide",
        )
        self.assertIsNone(normalize_keyword("quando lanca", topic, allow_unprefixed=True))

    def test_category_rules(self):
        topic = "animal hospital roblox"
        self.assertEqual(classify(f"{topic} active codes", topic), "codes")
        self.assertEqual(classify(f"{topic} veterinarian jobs", topic), "jobs")
        self.assertEqual(classify(f"{topic} beginner guide", topic), "guide")

    def test_extracts_and_merges_sources(self):
        topic = "animal hospital roblox"
        raw = {
            "labs": {
                "response": response_with_result(
                    {
                        "items": [
                            {
                                "keyword": f"{topic} codes",
                                "keyword_info": {"search_volume": 90, "monthly_searches": []},
                                "keyword_properties": {"core_keyword": f"{topic} code"},
                                "search_intent_info": {"main_intent": "informational"},
                            }
                        ]
                    }
                )
            },
            "trends": {
                "response": response_with_result(
                    {
                        "items": [
                            {
                                "type": "google_trends_queries_list",
                                "data": {
                                    "top": [{"query": f"{topic} codes", "value": "100"}],
                                    "rising": [{"query": f"{topic} jobs", "value": "Breakout"}],
                                },
                            }
                        ]
                    }
                )
            },
            "autocomplete": {
                "queries": [
                    {
                        "response": response_with_result(
                            {
                                "items": [
                                    {
                                        "type": "autocomplete",
                                        "suggestion": f"{topic} codes",
                                        "rank_absolute": 1,
                                    },
                                    {
                                        "type": "autocomplete",
                                        "suggestion": f"{topic} beginner guide",
                                        "rank_absolute": 2,
                                    },
                                ]
                            }
                        )
                    }
                ]
            },
            "youtube": {
                "response": response_with_result(
                    {
                        "items": [
                            {
                                "type": "youtube_video",
                                "title": "Animal Hospital Roblox Beginner Guide and Jobs",
                                "views_count": 10000,
                            }
                        ]
                    }
                )
            },
        }
        candidates, _ = extract_candidates(topic, raw)
        codes = next(item for item in candidates if item.keyword.endswith(" codes"))
        self.assertEqual(codes.sources, {"labs", "trends", "autocomplete"})
        self.assertEqual(codes.category, "codes")
        self.assertTrue(any(item.category == "guide" for item in candidates))

    def test_extracts_survival_game_topics_from_youtube_titles(self):
        topic = "hellhole roblox"
        raw = {
            "youtube": {
                "response": response_with_result(
                    {
                        "items": [
                            {
                                "type": "youtube_video",
                                "title": "HELLHOLE FULL GUIDE! (Enemies, Upgrades, Money) - Roblox",
                                "views_count": 100,
                            },
                            {
                                "type": "youtube_video",
                                "title": "SURVIVING EVERY FLOOR! ULTIMATE BOSS BATTLE! | HELLHOLE (ROBLOX)",
                                "views_count": 200,
                            },
                        ]
                    }
                )
            }
        }
        candidates, _ = extract_candidates(topic, raw)
        by_keyword = {item.keyword: item for item in candidates}
        for tail in ("full guide", "enemies", "upgrades", "money", "floor", "boss"):
            self.assertIn(f"{topic} {tail}", by_keyword)
        self.assertEqual(by_keyword[f"{topic} enemies"].category, "enemies")
        self.assertEqual(by_keyword[f"{topic} upgrades"].category, "upgrades")
        self.assertEqual(by_keyword[f"{topic} floor"].category, "floors")

    def test_multi_video_mechanics_create_stable_topics_but_single_video_does_not(self):
        topic = "timebomb duels roblox"
        raw = {
            "youtube": {
                "response": response_with_result(
                    {
                        "items": [
                            {
                                "type": "youtube_video",
                                "title": "I Tested Viral Jukes in Timebomb Duels",
                                "views_count": 40000,
                            },
                            {
                                "type": "youtube_video",
                                "title": "Breaking Ankles in Timebomb Duels",
                                "views_count": 70000,
                            },
                            {
                                "type": "youtube_video",
                                "title": "Passing the Bomb Like a Pro in Timebomb Duels",
                                "views_count": 5000,
                            },
                        ]
                    }
                )
            }
        }
        candidates, _ = extract_candidates(topic, raw)
        by_keyword = {item.keyword: item for item in candidates}
        stable = by_keyword[f"{topic} juking and movement guide"]
        self.assertEqual(stable.youtube_occurrences, 2)
        self.assertEqual(stable.youtube_views, 110000)
        self.assertNotIn(f"{topic} bomb passing techniques", by_keyword)

    def test_selection_and_validation(self):
        topic = "animal hospital roblox"
        candidates = []
        for keyword, category, score in [
            (f"{topic} codes", "codes", 100),
            (f"{topic} active codes", "codes", 90),
            (f"{topic} beginner guide", "guide", 80),
            (f"{topic} veterinarian jobs", "jobs", 70),
        ]:
            item = Candidate(keyword=keyword, category=category, score=score)
            candidates.append(item)
        selected = select_keywords(candidates)
        output = build_keywords_json(topic, selected)
        self.assertEqual(validate_keywords(output), [])
        codes = next(item for item in output["categories"] if item["category"] == "codes")
        self.assertEqual(len(codes["keywords"]), 1)

    def test_selection_limits_categories_and_merges_plural(self):
        topic = "animal hospital roblox"
        candidates = [
            Candidate(keyword=f"{topic} anomaly", category="anomalies", score=100),
            Candidate(keyword=f"{topic} anomalies", category="anomalies", score=90),
        ]
        for index in range(10):
            candidates.append(
                Candidate(keyword=f"{topic} topic {index}", category=f"cat{index}", score=80 - index)
            )
        candidates.append(Candidate(keyword=f"{topic} beginner guide", category="guide", score=1))
        selected = select_keywords(candidates)
        output = build_keywords_json(topic, selected)
        self.assertLessEqual(len(output["categories"]), 8)
        all_keywords = [keyword for category in output["categories"] for keyword in category["keywords"]]
        self.assertEqual(sum(keyword.endswith((" anomaly", " anomalies")) for keyword in all_keywords), 1)


if __name__ == "__main__":
    unittest.main()
