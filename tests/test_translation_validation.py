from __future__ import annotations

import sys
import unittest
from pathlib import Path


SEO_SCOUT_ROOT = Path(__file__).resolve().parents[1] / "pipeline" / "seo-scout"
sys.path.insert(0, str(SEO_SCOUT_ROOT))

from seoscout.translate import (
    _build_mdx,
    _compact_overlong_metadata,
    _process_llm_response,
    validate_translation_against_source,
)


SOURCE_BODY = """<Callout type="info">
**Quick Guide**

- Keep moving during combat.
</Callout>

## First Section

This paragraph is deliberately long enough to exercise the translation
checkpoint validator. It describes a complete section and ends normally.

### Details

| Item | Effect |
| --- | --- |
| Speed | Move faster. |

## FAQ

**Q1: Is this complete?**
Yes, this is the final answer.
"""


def translated_mdx(body: str) -> str:
    return _build_mdx("Titel", "Beschreibung", "guide", "2026-07-19", body)


class TranslationCompletenessTests(unittest.TestCase):
    def test_compacts_overlong_metadata_without_retranslating_body(self) -> None:
        title = "Codes Roblox Build an ASMR Tower : Votre guide des cadeaux gratuits"
        description = "Résumé français suffisamment précis pour décrire les codes, les récompenses et la procédure de réclamation dans le jeu."
        raw = f"TITLE: {title}\nDESCRIPTION: {description}\nBODY:\n{SOURCE_BODY}"

        compacted = _compact_overlong_metadata(raw, "fr")
        self.assertIsNotNone(compacted)
        content, error = _process_llm_response(
            compacted,
            "codes",
            "2026-07-20",
            SOURCE_BODY,
            "fr",
        )

        self.assertIsNotNone(content, error)
        self.assertIn(SOURCE_BODY, content)

    def test_accepts_structure_preserving_translation(self) -> None:
        ok, error = validate_translation_against_source(
            translated_mdx(SOURCE_BODY),
            SOURCE_BODY,
            "de",
        )
        self.assertTrue(ok, error)

    def test_rejects_truncated_heading_structure(self) -> None:
        truncated = SOURCE_BODY.split("## FAQ", 1)[0].rstrip() + "."
        ok, error = validate_translation_against_source(
            translated_mdx(truncated),
            SOURCE_BODY,
            "de",
        )
        self.assertFalse(ok)
        self.assertIn("Heading structure", error)

    def test_rejects_unclosed_callout(self) -> None:
        broken = SOURCE_BODY.replace("</Callout>", "")
        ok, error = validate_translation_against_source(
            translated_mdx(broken),
            SOURCE_BODY,
            "de",
        )
        self.assertFalse(ok)
        self.assertIn("Callout structure", error)

    def test_rejects_missing_final_formatted_question(self) -> None:
        broken = SOURCE_BODY.replace("**Q1: Is this complete?**\n", "")
        ok, error = validate_translation_against_source(
            translated_mdx(broken),
            SOURCE_BODY,
            "de",
        )
        self.assertFalse(ok)
        self.assertIn("formatted questions", error)


if __name__ == "__main__":
    unittest.main()
