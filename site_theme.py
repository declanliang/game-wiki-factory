"""Deterministic selection from contrast-tested site theme presets."""

from __future__ import annotations

import hashlib
import re


THEME_PRESETS = ("arcade", "forest", "ocean", "ember", "mystic", "industrial")

THEME_KEYWORDS = (
    ("forest", r"\b(animal|pet|garden|golf|forest|farm|nature|hospital)\b"),
    ("ocean", r"\b(ocean|sea|cove|island|fishing|pirate|water)\b"),
    ("ember", r"\b(horror|demon|hell|survival|evil|anomal|dragon|battle)\b"),
    ("mystic", r"\b(anime|magic|wizard|myth|unit|spirit|fantasy)\b"),
    ("industrial", r"\b(factory|simulator|builder|base|tycoon|machine|powerwash)\b"),
    ("arcade", r"\b(party|rng|race|sports?|arcade|co-?op)\b"),
)


def select_site_theme(
    game_name: str,
    description: str = "",
    categories: list[str] | None = None,
) -> dict[str, str]:
    haystack = " ".join([game_name, description, *(categories or [])]).casefold()
    for preset, pattern in THEME_KEYWORDS:
        if re.search(pattern, haystack, re.IGNORECASE):
            return {
                "schemaVersion": 1,
                "preset": preset,
                "selection": "semantic-rule",
            }
    digest = hashlib.sha256(game_name.casefold().encode("utf-8")).digest()
    preset = THEME_PRESETS[digest[0] % len(THEME_PRESETS)]
    return {
        "schemaVersion": 1,
        "preset": preset,
        "selection": "stable-fallback",
    }
