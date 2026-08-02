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
        self.assertIn("default hosting provider for every newly submitted site is Cloudflare Workers Static Assets", text)
        self.assertIn("Historical jobs may contain legacy `result.vercel` or `cloudflare-pages` receipts", text)
        self.assertIn("result.hosting.provider=cloudflare-workers-static-assets", text)
        self.assertIn("NEXT_PUBLIC_SITE_URL", text)
        self.assertNotIn("default hosting provider for every newly submitted site is Vercel", text)

    def test_server_wrapper_does_not_source_factory_env(self) -> None:
        wrapper = (ROOT / "deploy" / "gamewiki-server").read_text(encoding="utf-8")
        runner = (ROOT / "deploy" / "gamewiki-server-runner.py").read_text(encoding="utf-8")
        self.assertNotIn("source /srv/game-wiki-factory/secrets/factory.env", wrapper)
        self.assertIn("gamewiki-server-runner.py", wrapper)
        self.assertIn("parse_dotenv", runner)
        self.assertIn("os.execve", runner)


if __name__ == "__main__":
    unittest.main()
