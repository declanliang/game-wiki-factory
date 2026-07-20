from __future__ import annotations

import threading
import time
import unittest

from factory_cli import PermitState


class PermitStateTests(unittest.TestCase):
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
