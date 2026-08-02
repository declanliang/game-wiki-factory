import unittest
from pathlib import Path


class StaticAssetHeadersContractTests(unittest.TestCase):
    def test_hashed_next_assets_are_immutable(self):
        headers = (
            Path(__file__).resolve().parents[1] / "template" / "public" / "_headers"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "/_next/static/*\n  Cache-Control: public, max-age=31536000, immutable",
            headers,
        )

    def test_images_use_bounded_cache(self):
        headers = (
            Path(__file__).resolve().parents[1] / "template" / "public" / "_headers"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "/images/*\n  Cache-Control: public, max-age=86400, stale-while-revalidate=604800",
            headers,
        )

    def test_security_headers_remain_global(self):
        headers = (
            Path(__file__).resolve().parents[1] / "template" / "public" / "_headers"
        ).read_text(encoding="utf-8")
        self.assertTrue(headers.startswith("/*\n"))
        self.assertIn("X-Frame-Options: SAMEORIGIN", headers)


if __name__ == "__main__":
    unittest.main()
