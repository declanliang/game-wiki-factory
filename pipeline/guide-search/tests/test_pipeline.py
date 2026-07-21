import json
import tempfile
import unittest
from pathlib import Path

from get_search.llm_cluster import LLMCall
from get_search.pipeline import (
    load_context_checkpoint,
    load_run_metadata,
    slugify,
    total_cost,
    youtube_discovery_evidence,
    write_context_checkpoint,
    write_json,
)


class PipelineTests(unittest.TestCase):
    def test_youtube_discovery_evidence_deduplicates_and_ranks_video_titles(self):
        raw = {"youtube": {"items": [
            {"type": "youtube_video", "title": "Aizen guide", "url": "https://youtube.com/watch?v=1&x=2", "views_count": 50},
            {"type": "youtube_video", "title": "Aizen guide newer", "url": "https://youtube.com/watch?v=1", "views_count": 80},
            {"type": "youtube_video", "title": "Broly guide", "url": "https://youtube.com/watch?v=2", "views_count": 60},
            {"type": "youtube_channel", "title": "Ignore", "url": "https://youtube.com/c/x"},
        ]}}
        result = youtube_discovery_evidence(raw)
        self.assertEqual([item["title"] for item in result], ["Aizen guide newer", "Broly guide"])
        self.assertEqual(result[0]["url"], "https://youtube.com/watch?v=1")

    def test_context_checkpoint_requires_exact_candidate_and_model_match(self):
        call = LLMCall(
            model="context-model",
            data={"topic_name": "hellhole"},
            usage={"total_tokens": 42},
            cost_usd=None,
            response_meta={"model": "context-model", "web_search_used": True},
        )
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            write_context_checkpoint(run_dir, "Hellhole", ["hellhole codes"], "requested", call)
            cached = load_context_checkpoint(
                run_dir, "Hellhole", ["hellhole codes"], "requested"
            )
            wrong_candidates = load_context_checkpoint(
                run_dir, "Hellhole", ["hellhole guide"], "requested"
            )
            wrong_model = load_context_checkpoint(
                run_dir, "Hellhole", ["hellhole codes"], "different"
            )
        self.assertEqual(cached, call)
        self.assertIsNone(wrong_candidates)
        self.assertIsNone(wrong_model)

    def test_partial_raw_run_uses_explicit_topic_and_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            settings = type("SettingsStub", (), {"location": "United States", "language": "en"})()
            metadata = load_run_metadata(run_dir, "Hellhole", settings)
        self.assertEqual(metadata["topic"], "Hellhole")
        self.assertEqual(metadata["location"], "United States")
        self.assertEqual(metadata["google_suggest_source"], "cached")

    def test_partial_raw_run_without_topic_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "Provide the original topic"):
                load_run_metadata(Path(temporary), None, None)

    def test_slugify(self):
        self.assertEqual(slugify("Animal Hospital Roblox"), "animal-hospital-roblox")

    def test_total_cost(self):
        self.assertEqual(total_cost({"a": {"cost": 0.01}, "b": {"cost": 0.002}}), 0.012)

    def test_write_json_utf8(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nested" / "value.json"
            write_json(path, {"name": "测试"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["name"], "测试")


if __name__ == "__main__":
    unittest.main()
