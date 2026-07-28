"""Shared contract for staged locale publication.

English and Spanish are generated and quality-checked together. Only English is
initially public; Spanish is released three natural days later by a persistent
background job. Other template-supported locales are explicit Growth projects.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


GENERATED_LOCALES = ("en", "es")
LOCALE_RELEASE_ORDER = ("en", "es")
PUBLICATION_TIMEZONE = "Asia/Shanghai"
PUBLICATION_INTERVAL_DAYS = 3
PUBLICATION_HOUR = 10


def build_publication_plan(created_at: datetime | None = None) -> dict:
    """Return the v1_0728 generation/publication split for a new site."""
    instant = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "schemaVersion": 1,
        "generatedLocales": list(GENERATED_LOCALES),
        "publishedLocales": ["en"],
        "releasePolicy": {
            "mode": "sequential",
            "localeOrder": list(LOCALE_RELEASE_ORDER),
            "intervalDays": PUBLICATION_INTERVAL_DAYS,
            "timezone": PUBLICATION_TIMEZONE,
            "releaseHour": PUBLICATION_HOUR,
        },
        "createdAt": instant.replace(microsecond=0).isoformat(),
        "updatedAt": instant.replace(microsecond=0).isoformat(),
    }


def next_release_at(
    completed_at: datetime | None = None,
    *,
    interval_days: int = PUBLICATION_INTERVAL_DAYS,
    timezone_name: str = PUBLICATION_TIMEZONE,
    release_hour: int = PUBLICATION_HOUR,
) -> datetime:
    """Schedule the next wave on the third following local calendar day.

    This is deliberately based on calendar dates, not a fragile 72-hour sleep.
    If a delayed wave finishes later than planned, the next wave is scheduled
    from that actual completion date so multiple languages never appear at once.
    """
    instant = completed_at or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    zone = ZoneInfo(timezone_name)
    local = instant.astimezone(zone)
    target_date = local.date() + timedelta(days=max(1, interval_days))
    target_local = datetime.combine(
        target_date,
        time(hour=max(0, min(23, release_hour))),
        tzinfo=zone,
    )
    return target_local.astimezone(timezone.utc).replace(microsecond=0)


def next_locale(published_locales: list[str]) -> str | None:
    published = set(published_locales)
    return next(
        (locale for locale in LOCALE_RELEASE_ORDER if locale not in published),
        None,
    )


def validate_publication_plan(value: dict) -> None:
    if value.get("schemaVersion") != 1:
        raise ValueError("publication-plan schemaVersion must be 1")
    if value.get("generatedLocales") != list(GENERATED_LOCALES):
        raise ValueError("publication-plan generatedLocales must keep the fixed generation contract")
    published = value.get("publishedLocales")
    if not isinstance(published, list) or not published or published[0] != "en":
        raise ValueError("publication-plan publishedLocales must start with en")
    if len(published) != len(set(published)):
        raise ValueError("publication-plan publishedLocales contains duplicates")
    expected_prefix = list(LOCALE_RELEASE_ORDER[: len(published)])
    if published != expected_prefix:
        raise ValueError(
            "publication-plan publishedLocales must be a prefix of the locale release order"
        )
    policy = value.get("releasePolicy") or {}
    if policy.get("mode") != "sequential":
        raise ValueError("publication-plan releasePolicy.mode must be sequential")
    if policy.get("localeOrder") != list(LOCALE_RELEASE_ORDER):
        raise ValueError("publication-plan localeOrder is invalid")
    if policy.get("intervalDays") != PUBLICATION_INTERVAL_DAYS:
        raise ValueError("publication-plan intervalDays must be 3")
    if policy.get("timezone") != PUBLICATION_TIMEZONE:
        raise ValueError("publication-plan timezone must be Asia/Shanghai")

