from __future__ import annotations

import argparse
import json
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image

from .schemas import DEFAULT_LANGUAGE_CODES, TEMPLATE_SITE_CONTENT_SCHEMA, TEMPLATE_SITE_IDENTITY_SCHEMA
from .util import compact_number, dump_json, load_json, public_game_name


CONTRACT = "docs/contracts/site-input.md"
FORBIDDEN_KEYS = {
    "modules", "displayType", "themeColor", "sidebarCodes", "tertiaryCta",
    "title@home.hero", "secondaryCtaHref@home.hero", "videoId@home.hero",
    "explore@home", "start@home", "featured@home", "categories@home", "updates@home",
}
PLACEHOLDERS = {"unavailable", "unknown", "n/a", "none", "not found", "暂无", "未找到"}
HERO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}
FAVICON_FILES = (
    "favicon.ico",
    "favicon-16x16.png",
    "favicon-32x32.png",
    "apple-touch-icon.png",
    "android-chrome-192x192.png",
    "android-chrome-512x512.png",
    "site.webmanifest",
)
FAVICON_PNG_SIZES = {
    "favicon-16x16.png": (16, 16),
    "favicon-32x32.png": (32, 32),
    "apple-touch-icon.png": (180, 180),
    "android-chrome-192x192.png": (192, 192),
    "android-chrome-512x512.png": (512, 512),
}


def build_site_identity(facts: dict[str, Any]) -> dict[str, Any]:
    """Build the seven-key identity file; this homepage-only pipeline currently ships English."""
    identity = facts.get("identity", {})
    links = facts.get("officialLinks", {})
    return {
        "GAME_NAME": public_game_name(identity),
        "OFFICIAL_GAME_URL": identity.get("canonicalUrl") or links.get("steam") or links.get("roblox") or "",
        "DISCORD_URL": links.get("discord") or "",
        "YOUTUBE_CHANNEL_URL": _youtube_channel_value(links.get("youtube")),
        # Community wikis are not collected as official evidence; this optional value stays empty.
        "FANDOM_URL": "",
        "YOUTUBE_VIDEO_ID": _youtube_video_value(links.get("trailer")),
        "LANGUAGES": list(facts.get("languages") or DEFAULT_LANGUAGE_CODES),
    }


def build_site_content(facts: dict[str, Any], homepage: dict[str, Any]) -> dict[str, Any]:
    """Convert internal research output to the current two-key template intake format."""
    name = public_game_name(facts["identity"])
    official_name = str(facts["identity"].get("canonicalName") or "").strip()
    if official_name and official_name != name:
        homepage = _replace_public_name(homepage, official_name, name)
    platform = facts["identity"].get("platform") or "Game"
    game = facts.get("game", {})
    developer = facts.get("developer", {}).get("name") or ""
    publisher = facts.get("publisher", {}).get("name") or ""
    home = homepage.get("home", {})
    genres = _genres(facts, homepage)
    created_date = _date_only(game.get("createdAt"))
    updated_label = _month_year(game.get("updatedAt") or game.get("createdAt"))
    about_paragraphs = list(home.get("aboutGame", {}).get("paragraphs", []))[:3]
    site: dict[str, Any] = {
        "tagline": home.get("hero", {}).get("eyebrow") or "Fan-Made Community Wiki",
        "description": homepage.get("metadata", {}).get("description", ""),
        "legalNotice": f"Unofficial fan-made wiki. Not affiliated with {platform} or the game developer.",
        "gamePlatform": [platform],
    }
    if genres:
        site["genre"] = genres
    if created_date:
        site["datePublished"] = created_date
    if developer:
        site["developer"] = developer
    if publisher:
        site["publisher"] = publisher
    # Platform API price is evidence-backed when available.
    price = game.get("price")
    if isinstance(price, (int, float)):
        if platform == "Steam":
            site["price"] = "Free" if price == 0 else f"{price:.2f}"
            site["priceCurrency"] = game.get("priceCurrency") or ""
        else:
            site["price"] = "Free" if price == 0 else f"{price:g} Robux"
            site["priceCurrency"] = ""

    content: dict[str, Any] = {
        "site": site,
        "home": {
            "meta": {
                "title": home.get("meta", {}).get("title") or homepage.get("metadata", {}).get("title", ""),
                "description": home.get("meta", {}).get("description") or homepage.get("metadata", {}).get("description", ""),
            },
            "hero": {
                "eyebrow": home.get("hero", {}).get("eyebrow", ""),
                "description": home.get("hero", {}).get("description", ""),
                "stats": _hero_stats(facts, genres, updated_label),
            },
            "aboutGame": {
                "title": home.get("aboutGame", {}).get("title") or f"What is {name}?",
                "paragraphs": about_paragraphs,
                "stats": [item for item in [
                    {"label": "Developer", "value": developer} if developer else None,
                    {"label": "Platform", "value": platform},
                    {"label": "Genre", "value": " / ".join(genres)} if genres else None,
                ] if item],
            },
            "guideSections": list(home.get("guideSections") or []),
            "faq": {
                "title": "Frequently Asked Questions",
                "items": _faq_items(facts, about_paragraphs, genres),
            },
            "finalCta": {
                "title": home.get("finalCta", {}).get("title") or f"Ready to Play {name}?",
                "description": home.get("finalCta", {}).get("description", ""),
            },
        },
    }
    supported_codes = _supported_active_codes(facts)
    if supported_codes:
        content["home"]["liveTools"] = {
            "title": "Active & Community-Reported Codes",
            "items": [{
                "title": code["code"],
                "description": (
                    f"{_as_sentence(code['reward'])} Officially verified active code."
                    if code.get("officiallyVerified")
                    else f"{_as_sentence(code['reward'])} Community-reported active; verify in game."
                ),
                "href": "/codes",
                "category": "codes",
            } for code in supported_codes[:8]],
        }
    if not content["home"]["guideSections"]:
        content["home"].pop("guideSections")
    return content


def validate_site_identity(identity: dict[str, Any], facts: dict[str, Any]) -> list[dict[str, str]]:
    errors = _schema_errors(TEMPLATE_SITE_IDENTITY_SCHEMA, identity, "site-identity")
    expected = build_site_identity(facts)
    for key in ["GAME_NAME", "OFFICIAL_GAME_URL", "DISCORD_URL", "YOUTUBE_CHANNEL_URL", "YOUTUBE_VIDEO_ID", "LANGUAGES"]:
        if identity.get(key, "") != expected[key]:
            errors.append(_error("TEMPLATE_IDENTITY_FACT_MISMATCH", f"site-identity.{key}", f"{key} does not match evidence-backed facts.json."))
    for key, value in identity.items():
        if isinstance(value, str) and value.strip().casefold() in PLACEHOLDERS:
            errors.append(_error("TEMPLATE_PLACEHOLDER", f"site-identity.{key}", "Placeholder-like text is forbidden; use an empty string."))
    for key in ["OFFICIAL_GAME_URL", "DISCORD_URL", "YOUTUBE_CHANNEL_URL", "FANDOM_URL"]:
        value = identity.get(key, "")
        if value and not _valid_http_url(value):
            errors.append(_error("TEMPLATE_INVALID_URL", f"site-identity.{key}", "Value must be a complete http(s) URL."))
    return errors


def validate_site_content(content: dict[str, Any], facts: dict[str, Any]) -> list[dict[str, str]]:
    errors = _schema_errors(TEMPLATE_SITE_CONTENT_SCHEMA, content, "site-content")
    name = public_game_name(facts.get("identity", {}))
    expected_content = build_site_content(facts, {"metadata": {}, "home": {}})
    expected_site = expected_content.get("site", {})
    for key in ["gamePlatform", "datePublished", "developer", "publisher", "genre", "price", "priceCurrency"]:
        if key in content.get("site", {}) and content["site"].get(key) != expected_site.get(key):
            errors.append(_error("TEMPLATE_FACT_MISMATCH", f"site-content.site.{key}", f"{key} does not match evidence-backed facts.json."))
    if content.get("home", {}).get("hero", {}).get("stats") != expected_content.get("home", {}).get("hero", {}).get("stats"):
        errors.append(_error("TEMPLATE_FACT_MISMATCH", "site-content.home.hero.stats", "Hero stats do not match evidence-backed facts.json."))
    if content.get("home", {}).get("aboutGame", {}).get("stats") != expected_content.get("home", {}).get("aboutGame", {}).get("stats"):
        errors.append(_error("TEMPLATE_FACT_MISMATCH", "site-content.home.aboutGame.stats", "About-game stats do not match evidence-backed facts.json."))

    # Canonical names may contain non-Latin characters (for example the official
    # Roblox title "(学乱) Gakuran"). They are evidence-backed proper names, not
    # a language switch in otherwise English homepage copy. Exclude only these
    # exact facts from the English-language check.
    proper_names = {
        str(facts.get("identity", {}).get("canonicalName", "")).strip(),
        public_game_name(facts.get("identity", {})),
        str(facts.get("identity", {}).get("developer", "")).strip(),
        str(facts.get("developer", {}).get("name", "")).strip(),
        str(facts.get("publisher", {}).get("name", "")).strip(),
    }
    proper_names = sorted((name for name in proper_names if name), key=len, reverse=True)
    for path, value in _strings(content):
        normalized = value.strip().casefold()
        if "__" in value or "replace-with" in normalized or normalized in PLACEHOLDERS:
            errors.append(_error("TEMPLATE_PLACEHOLDER", "site-content." + path, f"Placeholder-like value is forbidden: {value}"))
        language_probe = value
        for proper_name in proper_names:
            language_probe = language_probe.replace(proper_name, "")
        if re.search(r"[\u3400-\u9fff]", language_probe):
            errors.append(_error("TEMPLATE_LANGUAGE", "site-content." + path, "Homepage content must be English."))

    for path, key in _keys(content):
        marker = f"{key}@{path}" if path else key
        if key in FORBIDDEN_KEYS or marker in FORBIDDEN_KEYS:
            errors.append(_error("TEMPLATE_FORBIDDEN_FIELD", f"site-content.{path}.{key}".replace("..", "."), f"Forbidden field: {key}"))

    hero_stats = content.get("home", {}).get("hero", {}).get("stats", [])
    about_stats = content.get("home", {}).get("aboutGame", {}).get("stats", [])
    hero_numbers = {_number_signature(item.get("value", "")) for item in hero_stats}
    hero_numbers.discard("")
    for index, item in enumerate(about_stats):
        signature = _number_signature(item.get("value", ""))
        if signature and signature in hero_numbers:
            errors.append(_error("TEMPLATE_DUPLICATE_STAT", f"site-content.home.aboutGame.stats.{index}.value", "Numeric fact duplicates a hero stat."))

    for index, item in enumerate(content.get("home", {}).get("faq", {}).get("items", [])):
        question = item.get("question", "")
        answer = item.get("answer", "")
        if name and name.casefold() not in question.casefold():
            errors.append(_error("TEMPLATE_FAQ_GAME_NAME", f"site-content.home.faq.items.{index}.question", "FAQ question must contain the canonical game name."))
        sentences = len([piece for piece in re.split(r"(?<=[.!?])\s+", answer.strip()) if piece]) if answer.strip() else 0
        if not 1 <= sentences <= 3:
            errors.append(_error("TEMPLATE_FAQ_LENGTH", f"site-content.home.faq.items.{index}.answer", "FAQ answer must contain 1–3 sentences."))

    expected_live_tools = build_site_content(facts, {"metadata": {}, "home": {}}).get("home", {}).get("liveTools")
    if "liveTools" in content.get("home", {}) and content["home"]["liveTools"] != expected_live_tools:
        errors.append(_error("TEMPLATE_LIVE_TOOL_FACT_MISMATCH", "site-content.home.liveTools", "liveTools must match sourced active or community-reported codes."))
    return errors


def validate_localized_site_content(
    localized: dict[str, Any],
    english: dict[str, Any],
    locale: str,
    facts: dict[str, Any],
) -> list[dict[str, str]]:
    """Validate a locale file against both the shared schema and the English source tree."""
    prefix = f"site-content.{locale}"
    errors = _schema_errors(TEMPLATE_SITE_CONTENT_SCHEMA, localized, prefix)
    _compare_locale_tree(english, localized, prefix, errors)

    name = public_game_name(facts.get("identity", {}))
    for path, english_value in _strings(english):
        localized_value = _value_at_path(localized, path)
        if not isinstance(localized_value, str):
            continue
        if _is_immutable_locale_path(path) and localized_value != english_value:
            errors.append(_error(
                "TEMPLATE_LOCALE_IMMUTABLE_MISMATCH", f"{prefix}.{path}",
                "href/category identifiers must exactly match site-content.json.",
            ))
        normalized_name = unicodedata.normalize("NFKC", name)
        normalized_localized_value = unicodedata.normalize("NFKC", localized_value)
        if name and name in english_value and normalized_name not in normalized_localized_value:
            errors.append(_error(
                "TEMPLATE_LOCALE_GAME_NAME", f"{prefix}.{path}",
                "The canonical game name must not be translated or removed.",
            ))
        expected_numbers = _number_signature(english_value)
        localized_numbers = _number_signature(localized_value)
        if expected_numbers != localized_numbers:
            errors.append(_error(
                "TEMPLATE_LOCALE_FACT_MISMATCH", f"{prefix}.{path}",
                f"Numeric facts must exactly match site-content.json; expected={expected_numbers!r}, got={localized_numbers!r}.",
            ))
        normalized = localized_value.strip().casefold()
        if "__" in localized_value or "replace-with" in normalized or normalized in PLACEHOLDERS:
            errors.append(_error("TEMPLATE_PLACEHOLDER", f"{prefix}.{path}", "Placeholder-like text is forbidden."))

    candidates = [
        (path, value) for path, value in _strings(english)
        if _is_translatable_prose(path, value, name)
    ]
    unchanged = [
        path for path, value in candidates
        if _value_at_path(localized, path) == value
    ]
    if candidates and (localized == english or len(unchanged) / len(candidates) >= 0.4):
        errors.append(_error(
            "TEMPLATE_LOCALE_NOT_TRANSLATED", prefix,
            f"Too much English prose was copied unchanged ({len(unchanged)}/{len(candidates)} strings).",
        ))
    return errors


def validate_template_contract(
    identity: dict[str, Any],
    content: dict[str, Any],
    facts: dict[str, Any],
    output_dir: Path | None = None,
    localized_contents: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    localized_contents = localized_contents or {}
    identity_errors = validate_site_identity(identity, facts)
    content_errors = validate_site_content(content, facts)
    locale_files: dict[str, dict[str, Any]] = {}
    locale_errors: list[dict[str, str]] = []
    required_locales = [code for code in identity.get("LANGUAGES", []) if code != "en"]
    for locale in required_locales:
        filename = f"site-content.{locale}.json"
        localized = localized_contents.get(locale)
        errors = (
            validate_localized_site_content(localized, content, locale, facts)
            if isinstance(localized, dict)
            else [_error("TEMPLATE_LOCALE_MISSING", filename, f"LANGUAGES declares {locale}, but {filename} is missing.")]
        )
        locale_files[filename] = {"status": "pass" if not errors else "fail", "errors": errors}
        locale_errors.extend(errors)
    for locale in sorted(set(localized_contents) - set(required_locales)):
        error = _error(
            "TEMPLATE_LOCALE_UNDECLARED", f"site-content.{locale}.json",
            f"Localized content exists for undeclared locale {locale}.",
        )
        locale_files[f"site-content.{locale}.json"] = {"status": "fail", "errors": [error]}
        locale_errors.append(error)
    asset_files: dict[str, dict[str, Any]] = {}
    asset_errors: list[dict[str, str]] = []
    if output_dir is not None:
        asset_files, asset_errors = validate_template_assets(output_dir)
    errors = identity_errors + content_errors + locale_errors + asset_errors
    return {
        "status": "pass" if not errors else "fail",
        "contract": CONTRACT,
        "files": {
            "site-identity.json": {"status": "pass" if not identity_errors else "fail", "errors": identity_errors},
            "site-content.json": {"status": "pass" if not content_errors else "fail", "errors": content_errors},
            **locale_files,
            **asset_files,
        },
        "errors": errors,
    }


def validate_template_assets(output_dir: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    """Validate the one-Hero plus complete favicon set required by the final intake package."""
    files: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    heroes = _hero_candidates(output_dir)
    if not heroes:
        hero_errors = [_error("TEMPLATE_ASSET_MISSING", "template-intake.hero", "No supported Hero image exists in assets/hero.")]
        files["hero"] = {"status": "fail", "errors": hero_errors}
        errors.extend(hero_errors)
    else:
        hero = heroes[0]
        hero_errors: list[dict[str, str]] = []
        try:
            with Image.open(hero) as image:
                width, height = image.size
                image.verify()
            if width / max(height, 1) < 1.3:
                hero_errors.append(_error("TEMPLATE_ASSET_INVALID", "template-intake.hero", f"Hero must be landscape; got {width}x{height}."))
        except Exception as exc:
            hero_errors.append(_error("TEMPLATE_ASSET_INVALID", "template-intake.hero", f"Hero cannot be decoded: {exc}"))
        files[f"hero{hero.suffix.lower()}"] = {"status": "pass" if not hero_errors else "fail", "source": str(hero), "errors": hero_errors}
        errors.extend(hero_errors)

    favicon_dir = output_dir / "assets" / "favicon"
    favicon_errors: list[dict[str, str]] = []
    for name in FAVICON_FILES:
        path = favicon_dir / name
        if not path.is_file():
            favicon_errors.append(_error("TEMPLATE_ASSET_MISSING", f"template-intake.favicon.{name}", "Required favicon file is missing."))
            continue
        try:
            if name == "site.webmanifest":
                manifest = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(manifest, dict):
                    raise ValueError("manifest root must be an object")
            else:
                with Image.open(path) as image:
                    size = image.size
                    image.verify()
                expected = FAVICON_PNG_SIZES.get(name)
                if expected and size != expected:
                    raise ValueError(f"expected {expected[0]}x{expected[1]}, got {size[0]}x{size[1]}")
        except Exception as exc:
            favicon_errors.append(_error("TEMPLATE_ASSET_INVALID", f"template-intake.favicon.{name}", f"Invalid favicon asset: {exc}"))
    files["favicon/"] = {"status": "pass" if not favicon_errors else "fail", "requiredFiles": list(FAVICON_FILES), "errors": favicon_errors}
    errors.extend(favicon_errors)
    return files, errors


def publish_template_package(
    output_dir: Path,
    identity: dict[str, Any],
    content: dict[str, Any],
    report: dict[str, Any],
    localized_contents: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Publish base JSON, one JSON per non-English locale, one Hero and favicon/."""
    localized_contents = localized_contents or {}
    identity_paths = [output_dir / "site-identity.json", output_dir / "template-intake" / "site-identity.json"]
    content_paths = [output_dir / "site-content.json", output_dir / "template-intake" / "site-content.json"]
    ready_dir = output_dir / "template-intake"
    staging_dir = output_dir / ".template-intake.tmp"
    invalid_identity = output_dir / "raw" / "site-identity.invalid.json"
    invalid_content = output_dir / "raw" / "site-content.invalid.json"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    localized_paths = list(output_dir.glob("site-content.??.json"))
    if report["errors"]:
        if ready_dir.exists():
            shutil.rmtree(ready_dir)
        for path in identity_paths + content_paths + localized_paths:
            path.unlink(missing_ok=True)
        dump_json(invalid_identity, identity)
        dump_json(invalid_content, content)
        for locale, localized in localized_contents.items():
            dump_json(output_dir / "raw" / f"site-content.{locale}.invalid.json", localized)
    else:
        invalid_identity.unlink(missing_ok=True)
        invalid_content.unlink(missing_ok=True)
        staging_dir.mkdir(parents=True)
        dump_json(staging_dir / "site-identity.json", identity)
        dump_json(staging_dir / "site-content.json", content)
        for locale, localized in sorted(localized_contents.items()):
            dump_json(staging_dir / f"site-content.{locale}.json", localized)
        hero_candidates = _hero_candidates(output_dir)
        hero = hero_candidates[0]
        shutil.copy2(hero, staging_dir / f"hero{hero.suffix.lower()}")
        gameplay_target = staging_dir / "gameplay-media"
        gameplay_target.mkdir()
        for index, gameplay_image in enumerate(hero_candidates[:5], 1):
            shutil.copy2(
                gameplay_image,
                gameplay_target / f"gameplay-{index}{gameplay_image.suffix.lower()}",
            )
        favicon_target = staging_dir / "favicon"
        favicon_target.mkdir()
        for name in FAVICON_FILES:
            shutil.copy2(output_dir / "assets" / "favicon" / name, favicon_target / name)
        if ready_dir.exists():
            shutil.rmtree(ready_dir)
        staging_dir.rename(ready_dir)
        dump_json(output_dir / "site-identity.json", identity)
        dump_json(output_dir / "site-content.json", content)
        for path in localized_paths:
            path.unlink(missing_ok=True)
        for locale, localized in sorted(localized_contents.items()):
            dump_json(output_dir / f"site-content.{locale}.json", localized)


def export_existing_output(output_dir: Path) -> dict[str, Any]:
    facts = load_json(output_dir / "facts.json")
    homepage = load_json(output_dir / "00首页信息.json")
    identity = build_site_identity(facts)
    content = build_site_content(facts, homepage)
    localized_contents = _load_existing_locales(output_dir, identity)
    report = validate_template_contract(identity, content, facts, output_dir, localized_contents)
    dump_json(output_dir / "template-validation-report.json", report)
    publish_template_package(output_dir, identity, content, report, localized_contents)
    _merge_validation_report(output_dir, report)
    return report


def _merge_validation_report(output_dir: Path, report: dict[str, Any]) -> None:
    validation_path = output_dir / "validation-report.json"
    if not validation_path.exists():
        return
    validation = load_json(validation_path)
    validation["errors"] = [error for error in validation.get("errors", []) if not error.get("code", "").startswith("TEMPLATE_")]
    validation["errors"].extend(report["errors"])
    validation.setdefault("metrics", {})["templateContractValid"] = report["status"] == "pass"
    validation["templateContract"] = report
    validation["status"] = "fail" if report["errors"] else ("warning" if validation.get("warnings") else "pass")
    dump_json(validation_path, validation)


def _schema_errors(schema: dict[str, Any], value: dict[str, Any], prefix: str) -> list[dict[str, str]]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [_error("TEMPLATE_SCHEMA_ERROR", prefix + "." + ".".join(map(str, issue.path)), issue.message)
            for issue in sorted(validator.iter_errors(value), key=lambda issue: [str(part) for part in issue.path])]


def _error(code: str, field: str, message: str) -> dict[str, str]:
    return {"code": code, "field": field.rstrip("."), "message": message}


def _hero_candidates(output_dir: Path) -> list[Path]:
    hero_dir = output_dir / "assets" / "hero"
    if not hero_dir.is_dir():
        return []
    return sorted(
        (path for path in hero_dir.iterdir() if path.is_file() and path.suffix.lower() in HERO_EXTENSIONS),
        key=lambda path: path.name.casefold(),
    )


def _supported_active_codes(facts: dict[str, Any]) -> list[dict[str, Any]]:
    """Allow sourced community reports while excluding unknown, expired or source-free codes."""
    return [
        code for code in facts.get("codes", [])
        if code.get("status") in {"verified-active", "claimed-active"}
        and len(str(code.get("code") or "").strip()) >= 2
        and bool(code.get("reward"))
        and bool(code.get("sourceUrls"))
    ]


def _genres(facts: dict[str, Any], homepage: dict[str, Any]) -> list[str]:
    game = facts.get("game", {})
    result: list[str] = []
    for value in [*(game.get("genres") or []), game.get("genreL1"), game.get("genreL2")]:
        if value and value.casefold() != "all" and value not in result:
            result.append(value)
    searchable = " ".join([game.get("officialDescription", "")] + [f"{item.get('name', '')} {item.get('value', '')}" for item in facts.get("gameplayFacts", [])]).casefold()
    if not result:
        if "tower defense" in searchable:
            result = ["Strategy", "Tower Defense"]
        elif "asymmetrical" in searchable and ("survival" in searchable or "survive" in searchable):
            result = ["Asymmetrical Survival"]
        elif "horror" in searchable and "survival" in searchable:
            result = ["Horror", "Survival"]
        elif "role-playing" in searchable or " rpg" in searchable:
            result = ["RPG"]
    if not result:
        about_stats = homepage.get("home", {}).get("aboutGame", {}).get("stats", [])
        candidate = next((item.get("value") for item in about_stats if item.get("label", "").casefold() == "genre"), None)
        if candidate and candidate.casefold() != "all":
            cleaned = re.sub(r"^all\s*[;/,-]*\s*", "", candidate, flags=re.I).strip()
            if cleaned:
                result = [cleaned]
    return result[:4]


def _hero_stats(facts: dict[str, Any], genres: list[str], updated_label: str) -> list[dict[str, str]]:
    game = facts.get("game", {})
    dynamic = facts.get("dynamicStats", {})
    platform = facts.get("identity", {}).get("platform")
    if platform == "Steam":
        candidates = [
            {"value": updated_label, "label": "Released"} if updated_label else None,
            {"value": compact_number(dynamic.get("reviewCount")), "label": "Steam Reviews"} if dynamic.get("reviewCount") else None,
            {"value": str(game.get("maxPlayers")), "label": "Co-op Players"} if game.get("maxPlayers") else None,
            {"value": "Early Access", "label": "Release Status"} if game.get("isEarlyAccess") else None,
            {"value": genres[0], "label": "Genre"} if genres else None,
            {"value": f"{dynamic.get('approvalPercent')}%", "label": "Positive Reviews"} if dynamic.get("approvalPercent") is not None else None,
            {"value": str(game.get("achievements")), "label": "Achievements"} if game.get("achievements") else None,
        ]
        return [item for item in candidates if item][:4]
    candidates = [
        {"value": updated_label, "label": "Updated"} if updated_label else None,
        {"value": compact_number(dynamic.get("visits")), "label": "Visits"} if dynamic.get("visits") else None,
        {"value": str(game.get("maxPlayers")), "label": "Players per Server"} if game.get("maxPlayers") else None,
        {"value": genres[-1], "label": "Core Mechanic"} if genres else None,
        {"value": f"{dynamic.get('approvalPercent')}%", "label": "Approval"} if dynamic.get("approvalPercent") is not None else None,
        {"value": compact_number(dynamic.get("favorites")), "label": "Favorites"} if dynamic.get("favorites") else None,
    ]
    return [item for item in candidates if item][:4]


def _faq_items(facts: dict[str, Any], paragraphs: list[str], genres: list[str]) -> list[dict[str, str]]:
    name = public_game_name(facts["identity"])
    developer = facts.get("developer", {}).get("name") or "the game developer"
    game = facts.get("game", {})
    platform = facts.get("identity", {}).get("platform") or "the official platform"
    items = [
        {"question": f"What is {name}?", "answer": _plain(paragraphs[0]) if paragraphs else f"{name} is a game available on {platform}."},
        {"question": f"Who developed {name}?", "answer": f"{name} is developed by {developer}."},
        {"question": f"Where can I play {name}?", "answer": f"You can play {name} through its official {platform} page."},
        {"question": f"When was {name} published?", "answer": f"{name} was released on {platform} on {_date_only(game.get('createdAt'))}."},
    ]
    if game.get("maxPlayers"):
        items.append({"question": f"How many players can join {name}?", "answer": f"The official description supports up to {game['maxPlayers']} players in one co-op session."})
    elif genres:
        items.append({"question": f"What genre is {name}?", "answer": f"{name} is categorized as {' / '.join(genres)}."})
    return items[:6]


def _date_only(value: str | None) -> str:
    return value[:10] if value and len(value) >= 10 else ""


def _month_year(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%b %Y")
    except ValueError:
        return ""


def _plain(value: str) -> str:
    return value.replace("**", "").strip()


def _replace_public_name(value: Any, official_name: str, display_name: str) -> Any:
    """Replace a platform-only alias in generated reader copy."""
    if isinstance(value, str):
        return value.replace(official_name, display_name)
    if isinstance(value, list):
        return [_replace_public_name(item, official_name, display_name) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_public_name(child, official_name, display_name)
            for key, child in value.items()
        }
    return value


def _as_sentence(value: str) -> str:
    cleaned = str(value).strip()
    return cleaned if cleaned.endswith((".", "!", "?")) else cleaned + "."


def _strings(value: Any, path: str = ""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _strings(child, f"{path}.{key}".strip("."))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _strings(child, f"{path}.{index}".strip("."))


def _keys(value: Any, path: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield path, key
            yield from _keys(child, f"{path}.{key}".strip("."))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _keys(child, f"{path}.{index}".strip("."))


def _compare_locale_tree(english: Any, localized: Any, path: str, errors: list[dict[str, str]]) -> None:
    if type(english) is not type(localized):
        errors.append(_error("TEMPLATE_LOCALE_STRUCTURE", path, "Value type differs from site-content.json."))
        return
    if isinstance(english, dict):
        if set(english) != set(localized):
            missing = sorted(set(english) - set(localized))
            extra = sorted(set(localized) - set(english))
            errors.append(_error(
                "TEMPLATE_LOCALE_STRUCTURE", path,
                f"Object keys must exactly match site-content.json; missing={missing}, extra={extra}.",
            ))
        for key in sorted(set(english) & set(localized)):
            _compare_locale_tree(english[key], localized[key], f"{path}.{key}", errors)
    elif isinstance(english, list):
        if len(english) != len(localized):
            errors.append(_error(
                "TEMPLATE_LOCALE_STRUCTURE", path,
                f"Array length must match site-content.json; expected {len(english)}, got {len(localized)}.",
            ))
        for index, (source, target) in enumerate(zip(english, localized)):
            _compare_locale_tree(source, target, f"{path}.{index}", errors)


def _value_at_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split(".") if path else []:
        try:
            current = current[int(part)] if isinstance(current, list) else current[part]
        except (KeyError, IndexError, TypeError, ValueError):
            return None
    return current


def _is_immutable_locale_path(path: str) -> bool:
    key = path.rsplit(".", 1)[-1]
    return (
        key in {"id", "href", "category"}
        or key.endswith("Href")
        or path in {"site.datePublished", "site.priceCurrency", "site.developer", "site.publisher"}
        or re.fullmatch(r"site\.gamePlatform\.\d+", path) is not None
        or re.fullmatch(r"home\.liveTools\.items\.\d+\.title", path) is not None
    )


def _is_translatable_prose(path: str, value: str, game_name: str) -> bool:
    if _is_immutable_locale_path(path) or not re.search(r"[A-Za-z]{3}", value):
        return False
    if value in {game_name, "Roblox", "Steam", "USD", "Free"} or re.fullmatch(r"\d[\d.,+% -]*", value):
        return False
    key = path.rsplit(".", 1)[-1]
    if key in {"datePublished", "priceCurrency", "developer", "publisher"}:
        return False
    return True


def _load_existing_locales(output_dir: Path, identity: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for locale in identity.get("LANGUAGES", []):
        if locale == "en":
            continue
        candidates = [
            output_dir / f"site-content.{locale}.json",
            output_dir / "template-intake" / f"site-content.{locale}.json",
        ]
        path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if path:
            result[locale] = load_json(path)
    return result


def _number_signature(value: str) -> str:
    return "".join(re.findall(r"\d+(?:\.\d+)?", str(value)))


def _youtube_video_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    pattern = r"^(?:[A-Za-z0-9_-]{11}|https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)[A-Za-z0-9_-]{11}(?:[?&#/].*)?)$"
    return value if re.fullmatch(pattern, value) else ""


def _youtube_channel_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    decoded = unquote(value.strip())
    parsed = urlparse(decoded)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.casefold() not in {"youtube.com", "www.youtube.com"}:
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if not parts or parts[0].casefold() in {"watch", "embed", "shorts", "live"}:
        return ""
    first = parts[0]
    if first.startswith("@"):
        canonical = first
    elif first.casefold() in {"channel", "c", "user"} and len(parts) >= 2:
        canonical = f"{first}/{parts[1]}"
    else:
        return ""
    return f"https://www.youtube.com/{canonical}"


def _valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and not any(char.isspace() for char in value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export existing output to a complete game-wiki-template intake package.")
    parser.add_argument("output_dirs", nargs="+", type=Path)
    args = parser.parse_args(argv)
    failed = False
    for directory in args.output_dirs:
        report = export_existing_output(directory.resolve())
        print(f"[{report['status']}] {directory}")
        failed = failed or report["status"] == "fail"
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
