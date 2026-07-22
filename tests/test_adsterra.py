from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from adsterra import PLACEMENTS, normalize_adsterra_config, resolve_project


def banner_code(width: int, height: int, key: str) -> str:
    return (
        "<script>atOptions = {"
        f"'key' : '{key}', 'format' : 'iframe', 'height' : {height}, "
        f"'width' : {width}, 'params' : {{}}"
        "};</script>"
        f'<script src="https://www.highperformanceformat.com/{key}/invoke.js"></script>'
    )


def sample_config() -> dict:
    placements = []
    for index, spec in enumerate(PLACEMENTS, start=1):
        token = f"token{index}"
        code = (
            '<script async="async" data-cfasync="false" '
            f'src="https://pl.example.effectivecpmnetwork.com/{token}/invoke.js"></script>'
            f'<div id="container-{token}"></div>'
            if spec.width is None
            else banner_code(spec.width, spec.height, token)
        )
        placements.append({
            "placement_id": str(30000000 + index),
            "title": spec.title,
            "alias": f"unit_{index}",
            "code": code,
        })
    return {
        "game": "Zenith Inc",
        "domain_id": "5928058",
        "domain_name": "zenith-inc-roblox.wiki",
        "placements": placements,
    }


class AdsterraTests(unittest.TestCase):
    def test_exact_titles_map_to_all_seven_slots(self) -> None:
        value = normalize_adsterra_config(sample_config())
        self.assertEqual([item["title"] for item in value["placements"]], [item.title for item in PLACEMENTS])
        self.assertEqual(value["domain_name"], "zenith-inc-roblox.wiki")

    def test_banner_title_and_dimensions_must_agree(self) -> None:
        value = sample_config()
        target = next(item for item in value["placements"] if item["title"] == "Banner 320x50")
        target["code"] = banner_code(728, 90, "wrongsize")
        with self.assertRaisesRegex(ValueError, "do not match 320x50"):
            normalize_adsterra_config(value)

    def test_missing_placement_is_rejected(self) -> None:
        value = sample_config()
        value["placements"].pop()
        with self.assertRaisesRegex(ValueError, "missing required"):
            normalize_adsterra_config(value)

    def test_game_identity_resolves_exact_local_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "zenith-inc"
            (project / "intake").mkdir(parents=True)
            (project / ".vercel").mkdir()
            (project / "intake" / "site-identity.json").write_text(
                json.dumps({"GAME_NAME": "Zenith Inc"}), encoding="utf-8"
            )
            (project / ".vercel" / "project.json").write_text(
                json.dumps({"projectName": "zenith-inc"}), encoding="utf-8"
            )
            resolved, vercel_name = resolve_project(sample_config(), Path(temporary))
            self.assertEqual(resolved, project.resolve())
            self.assertEqual(vercel_name, "zenith-inc")

    def test_rebuild_archive_is_never_an_ad_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for name in ("zenith-inc", "zenith-inc.pre-full-build-20260722T000000Z"):
                project = Path(temporary) / name
                (project / "intake").mkdir(parents=True)
                (project / ".vercel").mkdir()
                (project / "intake" / "site-identity.json").write_text(
                    json.dumps({"GAME_NAME": "Zenith Inc"}), encoding="utf-8"
                )
                (project / ".vercel" / "project.json").write_text(
                    json.dumps({"projectName": "zenith-inc"}), encoding="utf-8"
                )
            resolved, _ = resolve_project(sample_config(), Path(temporary))
            self.assertEqual(resolved.name, "zenith-inc")

    def test_wrong_game_cannot_match_domain_heuristic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "zenith-inc"
            (project / "intake").mkdir(parents=True)
            (project / "intake" / "site-identity.json").write_text(
                json.dumps({"GAME_NAME": "Another Game"}), encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "exactly one"):
                resolve_project(sample_config(), Path(temporary))


if __name__ == "__main__":
    unittest.main()
