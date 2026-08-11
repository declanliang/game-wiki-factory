"""Shared contract for locale publication.

New Factory sites generate and publish English only. Additional locales are
explicit post-launch Growth projects and are not scheduled by the core worker.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


GENERATED_LOCALES = ("en",)
LOCALE_RELEASE_ORDER = ("en",)
SUPPORTED_LOCALES = ("en", "es", "de", "fr", "ja")
PUBLICATION_TIMEZONE = "Asia/Shanghai"
PUBLICATION_INTERVAL_DAYS = 0
PUBLICATION_HOUR = 10


def build_publication_plan(created_at: datetime | None = None) -> dict:
    """Return the current generation/publication split for a new site."""
    instant = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "schemaVersion": 1,
        "generatedLocales": list(GENERATED_LOCALES),
        "publishedLocales": ["en"],
        "releasePolicy": {
            "mode": "english-only",
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


def next_locale_for_plan(value: dict) -> str | None:
    generated = value.get("generatedLocales") or []
    published = set(value.get("publishedLocales") or [])
    return next((locale for locale in generated if locale not in published), None)


def validate_publication_plan(value: dict) -> None:
    if value.get("schemaVersion") != 1:
        raise ValueError("publication-plan schemaVersion must be 1")
    generated = value.get("generatedLocales")
    if (
        not isinstance(generated, list)
        or not generated
        or generated[0] != "en"
        or len(generated) != len(set(generated))
        or any(locale not in SUPPORTED_LOCALES for locale in generated)
    ):
        raise ValueError("publication-plan generatedLocales must be an en-first supported locale subset")
    published = value.get("publishedLocales")
    if not isinstance(published, list) or not published or published[0] != "en":
        raise ValueError("publication-plan publishedLocales must start with en")
    if len(published) != len(set(published)):
        raise ValueError("publication-plan publishedLocales contains duplicates")
    expected_prefix = list(generated[: len(published)])
    if published != expected_prefix:
        raise ValueError(
            "publication-plan publishedLocales must be a prefix of the locale release order"
        )
    policy = value.get("releasePolicy") or {}
    expected_mode = "english-only" if generated == list(GENERATED_LOCALES) else "sequential"
    expected_interval = 0 if expected_mode == "english-only" else 3
    if policy.get("mode") != expected_mode:
        raise ValueError(f"publication-plan releasePolicy.mode must be {expected_mode}")
    if policy.get("localeOrder") != list(generated):
        raise ValueError("publication-plan localeOrder is invalid")
    if policy.get("intervalDays") != expected_interval:
        raise ValueError(f"publication-plan intervalDays must be {expected_interval}")
    if policy.get("timezone") != PUBLICATION_TIMEZONE:
        raise ValueError("publication-plan timezone must be Asia/Shanghai")

