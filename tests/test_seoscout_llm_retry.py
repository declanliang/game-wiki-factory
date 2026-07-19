from __future__ import annotations

import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


SEO_SCOUT_ROOT = Path(__file__).resolve().parents[1] / "pipeline" / "seo-scout"
sys.path.insert(0, str(SEO_SCOUT_ROOT))

from seoscout.core.config import Config
from seoscout.core.llm_client import LLMClient


class _FakeResponse:
    def __init__(self, payload, status=200, text=""):
        self.payload = payload
        self.status = status
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self.payload

    async def text(self):
        return self._text


class _FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.payloads = []

    def post(self, _url, *, json, headers, timeout):
        self.payloads.append(json)
        response = next(self.responses)
        return response if isinstance(response, _FakeResponse) else _FakeResponse(response)


def _response(content: str, finish_reason: str):
    return {
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
        "usage": {"total_tokens": 10},
    }


class LLMRetryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        Config.LLM_API_KEYS = ["test-key"]
        Config.LLM_API_KEY = "test-key"
        Config.LLM_API_BASE_URL = "https://example.invalid/v1"
        Config.LLM_MODEL = "test-model"
        Config.LLM_TEMPERATURE = 0.1
        Config.LLM_MAX_TOKENS = 24000
        Config.LLM_FREQUENCY_PENALTY = 0
        Config.LLM_PRESENCE_PENALTY = 0
        Config.LLM_TIMEOUT = 30
        Config.LLM_RETRY_ATTEMPTS = 2
        Config.LLM_RETRY_DELAY = 0
        Config.LLM_REASONING_EFFORT = "low"

    async def test_length_retry_uses_compact_fallback_and_generation_limit(self):
        client = LLMClient()
        client._save_debug = lambda *args, **kwargs: None
        session = _FakeSession([
            _response("partial", "length"),
            _response("complete", "stop"),
        ])

        with redirect_stdout(StringIO()):
            result = await client.generate_single(
                session,
                "original prompt",
                {"keyword": "test keyword"},
                max_tokens=10000,
                length_retry_instruction="Do not use Markdown tables.",
            )

        self.assertEqual(result, "complete")
        self.assertEqual([p["max_tokens"] for p in session.payloads], [10000, 10000])
        self.assertEqual(session.payloads[0]["messages"][1]["content"], "original prompt")
        self.assertIn("RETRY AFTER TRUNCATION", session.payloads[1]["messages"][1]["content"])
        self.assertIn("Do not use Markdown tables", session.payloads[1]["messages"][1]["content"])

    async def test_quota_error_disables_key_and_avoids_future_requests(self):
        Config.LLM_API_KEYS = ["quota-key"]
        client = LLMClient()
        session = _FakeSession([
            _FakeResponse(
                {},
                status=403,
                text='{"error":{"code":"insufficient_user_quota"}}',
            )
        ])

        with redirect_stdout(StringIO()):
            first = await client.generate_single(session, "prompt", {"keyword": "first"})
            second = await client.generate_single(session, "prompt", {"keyword": "second"})

        self.assertIsNone(first)
        self.assertIsNone(second)
        self.assertEqual(len(session.payloads), 1)


if __name__ == "__main__":
    unittest.main()
