from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OpenClawDeploymentDocsTests(unittest.TestCase):
    def test_operator_workspace_uses_cloudflare_contract(self) -> None:
        text = "\n".join(
            (ROOT / "deploy" / "openclaw" / name).read_text(encoding="utf-8")
            for name in ("AGENTS.md", "SOUL.md", "TOOLS.md")
        )
        self.assertIn("default hosting provider for every newly submitted site is Cloudflare Pages", text)
        self.assertIn("Historical jobs may contain legacy `result.vercel` receipts", text)
        self.assertIn("result.hosting.provider=cloudflare-pages", text)
        self.assertIn("NEXT_PUBLIC_SITE_URL", text)
        self.assertNotIn("Vercel", text)


if __name__ == "__main__":
    unittest.main()
