from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from seoscout.core.web import Web


class SeoScoutKeyPoolTests(unittest.TestCase):
    def test_serper_and_jina_slots_rotate_without_logging_values(self) -> None:
        web = Web()
        web.config = SimpleNamespace(
            SERPER_API_KEYS=["serper-one", "serper-two"],
            JINA_API_KEYS=["jina-one", "jina-two"],
        )

        async def exercise():
            return (
                await web._next_key("SERPER"),
                await web._next_key("SERPER"),
                await web._next_key("SERPER"),
                await web._next_key("JINA"),
                await web._next_key("JINA"),
            )

        result = asyncio.run(exercise())
        self.assertEqual([slot for slot, _key in result[:3]], [1, 2, 1])
        self.assertEqual([slot for slot, _key in result[3:]], [1, 2])


if __name__ == "__main__":
    unittest.main()
