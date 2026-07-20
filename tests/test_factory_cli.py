from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

from factory_cli import PermitState, _parse_game_spec, dispatch


class PermitStateTests(unittest.TestCase):
    def test_dispatch_keeps_status_output_utf8_safe(self) -> None:
        with patch("factory_cli.COMMANDS", {"fake": lambda argv: 0}):
            self.assertEqual(dispatch("fake", []), 0)

    def test_batch_tsv_preserves_per_game_platform_and_official_url(self) -> None:
        url = "https://www.roblox.com/games/106763540857326/Blox-Monsters"
        task = _parse_game_spec(f"Blox Monsters\troblox\t{url}")
        self.assertEqual(task["game"], "Blox Monsters")
        self.assertEqual(task["platform"], "roblox")
        self.assertEqual(task["args"], ["--platform", "roblox", "--official-url", url])

    def test_batch_plain_name_remains_backward_compatible(self) -> None:
        self.assertEqual(_parse_game_spec("Hellhole"), {"game": "Hellhole", "args": []})

    def test_per_key_limit_is_global_and_release_unblocks_waiter(self) -> None:
        state = PermitState(llm_limit=2, per_key_limit=1, build_limit=1)
        first = state.acquire(["llm", "llm-key-1"])
        acquired: list[str] = []

        def wait_for_same_key():
            acquired.append(state.acquire(["llm", "llm-key-1"]))

        thread = threading.Thread(target=wait_for_same_key)
        thread.start()
        time.sleep(0.05)
        self.assertEqual(acquired, [])
        state.release(first)
        thread.join(timeout=1)
        self.assertEqual(len(acquired), 1)
        state.release(acquired[0])

    def test_different_key_slots_share_global_llm_limit(self) -> None:
        state = PermitState(llm_limit=2, per_key_limit=1, build_limit=1)
        leases = [state.acquire(["llm", f"llm-key-{slot}"]) for slot in (1, 2)]
        self.assertEqual(state.in_use["llm"], 2)
        for lease in leases:
            state.release(lease)


if __name__ == "__main__":
    unittest.main()
