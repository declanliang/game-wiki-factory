from __future__ import annotations

import unittest

from site_theme import select_site_theme


class SiteThemeTests(unittest.TestCase):
    def test_theme_uses_semantic_game_context(self) -> None:
        self.assertEqual(
            select_site_theme("Heave Ho 2", "A co-op party challenge", ["modes"])["preset"],
            "arcade",
        )
        self.assertEqual(
            select_site_theme("Animal Clinic", "Treat pets in a hospital", ["animals"])["preset"],
            "forest",
        )
        self.assertEqual(
            select_site_theme("Corsair Cove", "Explore a pirate island", ["locations"])["preset"],
            "ocean",
        )

    def test_theme_fallback_is_stable(self) -> None:
        first = select_site_theme("Unclassified Game")
        second = select_site_theme("Unclassified Game")
        self.assertEqual(first, second)
        self.assertEqual(first["selection"], "stable-fallback")
