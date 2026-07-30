from __future__ import annotations

import base64
import unittest

from ad_profile import AD_ENV_NAMES, load_shared_ad_environment


class SharedAdProfileTests(unittest.TestCase):
    def test_profile_provides_complete_round_trippable_contract(self) -> None:
        environment = load_shared_ad_environment()
        self.assertEqual(tuple(environment), AD_ENV_NAMES)
        self.assertEqual(len(environment), 8)
        for value in environment.values():
            self.assertNotIn("\n", value)
            snippet = base64.b64decode(value).decode("utf-8")
            self.assertIn("<script", snippet.casefold())
            self.assertIn("invoke.js", snippet.casefold())

    def test_desktop_and_mobile_native_use_distinct_placements(self) -> None:
        environment = load_shared_ad_environment()
        desktop = base64.b64decode(environment["AD_NATIVE_BANNER_B64"]).decode("utf-8")
        mobile = base64.b64decode(environment["AD_NATIVE_BANNER_MOBILE_B64"]).decode("utf-8")
        self.assertNotEqual(desktop, mobile)
        self.assertIn("5644a054d66cb50289b62eb195ec0a41", desktop)
        self.assertIn("e0128edd35ab5cd83be7f955b4e0b66d", mobile)


if __name__ == "__main__":
    unittest.main()
