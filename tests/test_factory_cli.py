from __future__ import annotations

import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from factory_cli import PermitState, _config_command, _parse_game_spec, dispatch, run_config


class PermitStateTests(unittest.TestCase):
    def test_config_normalizes_game_whitespace_and_maps_options(self) -> None:
        game, args = _config_command({
            "game": "Build A Blue Lock Squad\n",
            "platform": "ROBLOX",
            "officialUrl": " https://www.roblox.com/games/1/example ",
            "siteUrl": "example.wiki",
            "publish": True,
            "refresh": {"basicInfo": False, "keywords": True, "articles": False},
        })
        self.assertEqual(game, "Build A Blue Lock Squad")
        self.assertEqual(args, [
            "--platform", "roblox",
            "--official-url", "https://www.roblox.com/games/1/example",
            "--site-url", "example.wiki",
            "--publish", "--recluster-keywords",
        ])

    def test_config_rejects_unknown_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown config field"):
            _config_command({"game": "Example", "publsh": True})

    def test_run_config_saves_full_log_and_config_outside_git_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "factory"
            projects = root.parent
            runtime = root / ".gamewiki" / "runs"
            root.mkdir()
            config_path = root / "game.json"
            config_path.write_text(json.dumps({"game": "Test Game", "platform": "roblox"}), encoding="utf-8")
            project_state = projects / "test-game" / ".gamewiki"
            project_state.mkdir(parents=True)
            process = unittest.mock.MagicMock()
            process.stdout = io.StringIO("complete output\n")
            process.wait.return_value = 0
            with (
                patch("factory_cli.ROOT", root),
                patch("factory_cli.PROJECTS_ROOT", projects),
                patch("factory_cli.RUNTIME_ROOT", runtime),
                patch("factory_cli.subprocess.Popen", return_value=process),
            ):
                self.assertEqual(run_config([str(config_path)]), 0)
            self.assertEqual(len(list((project_state / "configs").glob("*.json"))), 1)
            saved_logs = list((project_state / "logs").glob("*-config.log"))
            self.assertEqual(len(saved_logs), 1)
            self.assertIn("complete output", saved_logs[0].read_text(encoding="utf-8"))

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
