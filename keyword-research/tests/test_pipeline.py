import json
import tempfile
import unittest
from pathlib import Path

from get_search.pipeline import slugify, total_cost, write_json


class PipelineTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("Animal Hospital Roblox"), "animal-hospital-roblox")

    def test_total_cost(self):
        self.assertEqual(total_cost({"a": {"cost": 0.01}, "b": {"cost": 0.002}}), 0.012)

    def test_write_json_utf8(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nested" / "value.json"
            write_json(path, {"name": "测试"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["name"], "测试")


if __name__ == "__main__":
    unittest.main()
