from __future__ import annotations

import unittest
from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[1] / "template"


class TemplateLayoutContractTests(unittest.TestCase):
    def test_root_layout_owns_html_and_body_shell(self) -> None:
        root = (TEMPLATE / "src" / "app" / "layout.tsx").read_text(encoding="utf-8")
        locale = (
            TEMPLATE / "src" / "app" / "[locale]" / "layout.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("<html lang=", root)
        self.assertIn("<body>", root)
        self.assertNotIn("<html", locale)
        self.assertNotIn("<body", locale)
        self.assertIn("NextIntlClientProvider", locale)

