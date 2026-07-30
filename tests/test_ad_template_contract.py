from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template"


class AdTemplateContractTests(unittest.TestCase):
    def test_mobile_native_is_mapped_across_runtime_layers(self) -> None:
        expected = "AD_NATIVE_BANNER_MOBILE_B64"
        for relative in (
            "src/lib/ad-config.ts",
            "functions/api/ads/availability.ts",
            "functions/api/ads/[format].ts",
            ".env.example",
        ):
            content = (TEMPLATE / relative).read_text(encoding="utf-8")
            self.assertIn(expected, content, relative)

    def test_ad_iframe_has_no_sandbox_and_keeps_isolation_route(self) -> None:
        content = (TEMPLATE / "src/components/ad-slot.tsx").read_text(encoding="utf-8")
        self.assertNotIn("sandbox=", content)
        self.assertIn('src={`/api/ads/${format}`}', content)
        self.assertIn('referrerPolicy="strict-origin-when-cross-origin"', content)

    def test_native_flow_waits_for_viewport_and_selects_one_format(self) -> None:
        content = (TEMPLATE / "src/components/ad-placements.tsx").read_text(encoding="utf-8")
        self.assertIn("useState<boolean | null>(null)", content)
        self.assertIn("if (desktop === null) return null", content)
        self.assertIn('format="nativeBanner"', content)
        self.assertIn('format="nativeBannerMobile"', content)
        self.assertIn("aspect-square", content)

    def test_article_rail_ad_is_left_only(self) -> None:
        content = (TEMPLATE / "src/components/ad-placements.tsx").read_text(encoding="utf-8")
        rail = content.split("export function DesktopArticleRailAds()", 1)[1].split(
            "export function ArticleInlineAd", 1
        )[0]
        self.assertIn('left: "calc(50% - 632px)"', rail)
        self.assertIn('aria-label="Left advertisement"', rail)
        self.assertNotIn("right:", rail)
        self.assertNotIn("Right advertisement", rail)


if __name__ == "__main__":
    unittest.main()
