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
            "src/worker.ts",
            "functions/api/ads/availability.ts",
            "functions/api/ads/[format].ts",
            ".env.example",
        ):
            content = (TEMPLATE / relative).read_text(encoding="utf-8")
            self.assertIn(expected, content, relative)

    def test_ad_iframe_has_no_sandbox_and_keeps_isolation_route(self) -> None:
        content = (TEMPLATE / "src/components/ad-slot.tsx").read_text(encoding="utf-8")
        self.assertNotIn("sandbox=", content)
        self.assertIn('src={`${AD_RENDER_ROUTE}/${format}`}', content)
        self.assertIn('const AD_RENDER_ROUTE = "/api/ads/render"', content)
        self.assertIn('referrerPolicy="strict-origin-when-cross-origin"', content)

    def test_worker_ad_routes_defeat_browser_html_cache_variants(self) -> None:
        content = (TEMPLATE / "src/worker.ts").read_text(encoding="utf-8")
        self.assertIn('"/api/ads/availability"', content)
        self.assertIn(r"/^\/api\/ads\/(?:render\/)?([^/]+)\/?$/", content)
        self.assertIn('"CDN-Cache-Control": "no-store"', content)
        self.assertIn('"Cloudflare-CDN-Cache-Control": "no-store"', content)
        self.assertIn('Vary: "Accept"', content)
        self.assertIn('request.method === "HEAD"', content)

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

    def test_sticky_navigation_reserves_the_top_ad_height(self) -> None:
        content = (TEMPLATE / "src/components/site.tsx").read_text(encoding="utf-8")
        self.assertIn('style={{ top: "var(--top-ad-height, 0px)" }}', content)
        self.assertIn('className="sticky z-50 border-b border-border bg-background"', content)
        self.assertNotIn("bg-background/90", content)
        self.assertNotIn('className="sticky top-0', content)

    def test_top_ad_uses_the_same_opaque_background_as_navigation(self) -> None:
        content = (TEMPLATE / "src/components/ad-placements.tsx").read_text(encoding="utf-8")
        top_ad = content.split("export function TopStickyAd()", 1)[1].split(
            "export function NativeFlowAd", 1
        )[0]
        self.assertIn("justify-center bg-background", top_ad)

    def test_global_footer_selects_exactly_one_responsive_format(self) -> None:
        content = (TEMPLATE / "src/components/ad-placements.tsx").read_text(encoding="utf-8")
        footer = content.split("export function GlobalFooterAds()", 1)[1].split(
            "export function DesktopBanner728", 1
        )[0]
        self.assertIn('useResolvedMediaQuery("(min-width: 900px)")', footer)
        self.assertIn("if (desktop === null) return null", footer)
        self.assertEqual(footer.count("<AdSlot"), 1)
        self.assertIn("<AdSlot format={format}", footer)

    def test_category_and_article_pages_do_not_add_terminal_ad_groups(self) -> None:
        content = (TEMPLATE / "src/app/[locale]/[...slug]/page.tsx").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("DesktopFooterAdGroup", content)
        self.assertNotIn("DesktopBanner728", content)
        self.assertNotIn('format="banner300x250"', content)
        self.assertIn("cardItems.length >= 4 && index === 1", content)

    def test_inline_article_ads_exclude_nested_blocks_and_article_tail(self) -> None:
        placements = (TEMPLATE / "src/components/ad-placements.tsx").read_text(
            encoding="utf-8"
        )
        inline = placements.split("export function ArticleInlineAd", 1)[1]
        self.assertIn("Array.from(container.children)", inline)
        self.assertIn('node.closest("[data-ad-exclusion]")', inline)
        self.assertIn("paragraphs.length - 5", inline)
        self.assertIn("Math.floor(paragraphs.length * 0.75) - 1", inline)
        self.assertIn("paragraphs.length >= 23 ? 3", inline)
        self.assertIn("paragraphs.length >= 14 ? 2", inline)
        self.assertIn("paragraphs.length >= 8 ? 1", inline)
        for relative in ("src/mdx-components.tsx", "src/components/mdx/Callout.tsx"):
            content = (TEMPLATE / relative).read_text(encoding="utf-8")
            self.assertIn('data-ad-exclusion="callout"', content, relative)

    def test_homepage_ads_are_siblings_between_editorial_sections(self) -> None:
        homepage = (TEMPLATE / "src/app/[locale]/HomePageClient.tsx").read_text(
            encoding="utf-8"
        )
        light_section = homepage.split("function LightSectionBlock", 1)[1].split(
            "function GuideSectionsBlock", 1
        )[0]
        self.assertNotIn("ResponsiveContentAd", light_section)
        self.assertNotIn("insertAd", light_section)
        self.assertIn('data-ad-exclusion="section"', light_section)
        self.assertIn('case "sectionAd"', homepage)
        self.assertIn('aria-label="Section advertisement"', homepage)

        order = (TEMPLATE / "src/config/home.ts").read_text(encoding="utf-8")
        self.assertLess(order.index('"featured"'), order.index('"sectionAd"'))
        self.assertLess(order.index('"sectionAd"'), order.index('"about"'))
        self.assertNotIn('"bottomAd"', order)


if __name__ == "__main__":
    unittest.main()
