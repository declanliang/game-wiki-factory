from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from migrate_language_policy import migrate


class LanguagePolicyMigrationTests(unittest.TestCase):
    def test_removes_retired_locale_without_touching_supported_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "site"
            (project / "intake" / "articles" / "en").mkdir(parents=True)
            (project / "intake" / "articles" / "ko").mkdir(parents=True)
            (project / "content" / "ko").mkdir(parents=True)
            (project / "src" / "locales").mkdir(parents=True)
            (project / "package.json").write_text("{}", encoding="utf-8")
            (project / "intake" / "site-identity.json").write_text(
                json.dumps({"LANGUAGES": ["en", "es", "de", "fr", "ja", "ko"]}), encoding="utf-8"
            )
            (project / "intake" / "site-plan.json").write_text(
                json.dumps({
                    "languages": ["en", "es", "de", "fr", "ja", "ko"],
                    "categories": [{
                        "labels": {locale: locale for locale in ["en", "es", "de", "fr", "ja", "ko"]},
                        "descriptions": {locale: locale for locale in ["en", "es", "de", "fr", "ja", "ko"]},
                    }],
                }),
                encoding="utf-8",
            )
            (project / "intake" / "site-content.ko.json").write_text("{}", encoding="utf-8")
            (project / "src" / "locales" / "ko.json").write_text("{}", encoding="utf-8")

            self.assertEqual(migrate(project), ["ko"])
            plan = json.loads((project / "intake" / "site-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["languages"], ["en", "es", "de", "fr", "ja"])
            self.assertNotIn("ko", plan["categories"][0]["labels"])
            self.assertTrue((project / "intake" / "articles" / "en").is_dir())
            self.assertFalse((project / "intake" / "articles" / "ko").exists())
            self.assertFalse((project / "content" / "ko").exists())


if __name__ == "__main__":
    unittest.main()
