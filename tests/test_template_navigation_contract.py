from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template"


class TemplateNavigationContractTests(unittest.TestCase):
    def test_homepage_internal_links_stay_same_tab_and_external_links_open_new(self) -> None:
        homepage = (TEMPLATE / "src/app/[locale]/HomePageClient.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("const newTabLinkProps", homepage)
        self.assertIn("function linkPropsForHref", homepage)
        self.assertIn('target: "_blank"', homepage)
        self.assertIn('rel: "noopener noreferrer"', homepage)
        self.assertGreaterEqual(homepage.count("linkPropsForHref("), 10)
        self.assertIn("step.external ? newTabLinkProps", homepage)
        self.assertNotIn("{...newTabLinkProps}", homepage)

    def test_global_site_navigation_stays_same_tab(self) -> None:
        site_shell = (TEMPLATE / "src/components/site.tsx").read_text(
            encoding="utf-8"
        )

        self.assertNotIn('target="_blank"', site_shell)
        self.assertNotIn("newTabLinkProps", site_shell)


if __name__ == "__main__":
    unittest.main()
