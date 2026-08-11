from __future__ import annotations

import unittest
from datetime import datetime, timezone

from publication_plan import (
    build_publication_plan,
    next_locale,
    next_release_at,
    validate_publication_plan,
)


class PublicationPlanTests(unittest.TestCase):
    def test_new_site_generates_and_publishes_english_only(self) -> None:
        plan = build_publication_plan(datetime(2026, 7, 28, 4, 30, tzinfo=timezone.utc))
        self.assertEqual(plan["generatedLocales"], ["en"])
        self.assertEqual(plan["publishedLocales"], ["en"])
        self.assertEqual(plan["releasePolicy"]["mode"], "english-only")
        self.assertEqual(plan["releasePolicy"]["intervalDays"], 0)
        self.assertEqual(plan["releasePolicy"]["timezone"], "Asia/Shanghai")
        validate_publication_plan(plan)

    def test_next_wave_helper_can_still_use_third_following_shanghai_calendar_day(self) -> None:
        # 12:30 in Shanghai on Jul 28 -> 10:00 on Jul 31 -> 02:00 UTC.
        scheduled = next_release_at(
            datetime(2026, 7, 28, 4, 30, tzinfo=timezone.utc),
            interval_days=3,
        )
        self.assertEqual(scheduled, datetime(2026, 7, 31, 2, 0, tzinfo=timezone.utc))

    def test_release_order_is_fixed_and_prefix_only(self) -> None:
        self.assertIsNone(next_locale(["en"]))
        plan = build_publication_plan()
        plan["publishedLocales"] = ["en", "de"]
        with self.assertRaisesRegex(ValueError, "prefix"):
            validate_publication_plan(plan)

    def test_explicit_growth_locale_plan_can_still_be_validated(self) -> None:
        plan = build_publication_plan()
        plan["generatedLocales"] = ["en", "es"]
        plan["releasePolicy"]["mode"] = "sequential"
        plan["releasePolicy"]["localeOrder"] = ["en", "es"]
        plan["releasePolicy"]["intervalDays"] = 3
        validate_publication_plan(plan)
