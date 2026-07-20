from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from publisher import _validate_project


class PublisherValidationTests(unittest.TestCase):
    def _project(self, root: Path) -> Path:
        (root / ".gamewiki").mkdir()
        (root / "intake").mkdir()
        (root / ".gamewiki" / "manifest.json").write_text(json.dumps({"status": "complete"}), encoding="utf-8")
        (root / "package.json").write_text("{}", encoding="utf-8")
        for name in ("site-identity.json", "site-content.json", "site-plan.json"):
            (root / "intake" / name).write_text("{}", encoding="utf-8")
        return root

    def test_complete_project_is_publishable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = _validate_project(self._project(Path(temporary)))
        self.assertEqual(manifest["status"], "complete")

    def test_secret_file_blocks_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self._project(Path(temporary))
            (project / ".env.production").write_text("TOKEN=secret", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Secret-like"):
                _validate_project(project)


if __name__ == "__main__":
    unittest.main()
