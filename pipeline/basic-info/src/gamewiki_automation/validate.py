from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker

from .schemas import HOMEPAGE_SCHEMA, MODULES_SCHEMA
from .template_contract import validate_template_contract


BLOCKED_DOMAINS = ("fandom.com", "wiki.gg", "fextralife.com")


def _schema_errors(value: Any, schema: dict[str, Any], prefix: str) -> list[dict[str, str]]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        {"code": "SCHEMA_ERROR", "field": prefix + "." + ".".join(map(str, error.path)), "message": error.message}
        for error in sorted(validator.iter_errors(value), key=lambda e: list(e.path))
    ]


def validate_package(facts: dict[str, Any], evidence: dict[str, Any], homepage: dict[str, Any], modules: dict[str, Any], media: dict[str, Any], calls: list[dict[str, Any]], site_identity: dict[str, Any], site_content: dict[str, Any], output_dir: Path, localized_contents: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    errors = _schema_errors(homepage, HOMEPAGE_SCHEMA, "homepage") + _schema_errors(modules, MODULES_SCHEMA, "modules")
    template_report = validate_template_contract(site_identity, site_content, facts, output_dir, localized_contents)
    template_errors = template_report["errors"]
    errors.extend(template_errors)
    warnings: list[dict[str, str]] = []
    identity = facts.get("identity", {})
    platform = identity.get("platform")
    required_platform_ids = (
        [identity.get("appId")]
        if platform == "Steam"
        else [identity.get("placeId"), identity.get("universeId")]
    )
    if not all(required_platform_ids) or not identity.get("canonicalUrl") or identity.get("matchConfidence", 0) < 0.72:
        errors.append({"code": "IDENTITY_UNCERTAIN", "field": "facts.identity", "message": f"{platform or 'Platform'} identity is incomplete or below confidence threshold."})
    if not facts.get("officialLinks", {}).get("discord"):
        warnings.append({"code": "MISSING_OFFICIAL_DISCORD", "field": "facts.officialLinks.discord", "message": "No verifiable official Discord was found."})
    if not facts.get("officialLinks", {}).get("trailer"):
        warnings.append({"code": "MISSING_OFFICIAL_TRAILER", "field": "facts.officialLinks.trailer", "message": "No verifiable official trailer was found."})
    if any(code.get("status") == "claimed-active" for code in facts.get("codes", [])):
        warnings.append({"code": "UNVERIFIED_CODES", "field": "facts.codes", "message": "Some codes are supported only by third-party sources."})
    if media.get("errors"):
        warnings.append({"code": "MEDIA_PARTIAL", "field": "assets", "message": "; ".join(media["errors"][:4])})
    if facts.get("languageMarket", {}).get("partial"):
        warnings.append({"code": "LANGUAGE_RESEARCH_PARTIAL", "field": "facts.languageMarket", "message": "Dedicated language-market research could not fully check every major candidate market."})
    orders = [m.get("order") for m in modules.get("modules", [])]
    if orders and orders != list(range(1, len(orders) + 1)):
        errors.append({"code": "MODULE_ORDER", "field": "modules.modules", "message": "Module orders must be unique and contiguous from 1."})
    for idx, module in enumerate(modules.get("modules", [])):
        for url in module.get("references", []):
            host = (urlparse(url).hostname or "").lower()
            if any(host == domain or host.endswith("." + domain) for domain in BLOCKED_DOMAINS):
                errors.append({"code": "BLOCKED_REFERENCE", "field": f"modules.modules.{idx}.references", "message": f"Blocked competitor/wiki reference: {url}"})
    sources = evidence.get("sources", [])
    claims = evidence.get("claims", [])
    source_ids = {s.get("id") for s in sources}
    claims_with_sources = sum(bool(set(c.get("sourceIds", [])) & source_ids) for c in claims)
    official_sources = sum(s.get("sourceType") in {"official-api", "official-platform", "official-creator", "official-social"} for s in sources)
    required_checks = [*required_platform_ids, identity.get("canonicalUrl"), facts.get("developer", {}).get("name"), homepage.get("home"), modules.get("modules")]
    cost = _cost_summary(calls)
    status = "fail" if errors else "warning" if warnings else "pass"
    return {
        "status": status, "errors": errors, "warnings": warnings,
        "metrics": {
            "requiredFieldsComplete": round(sum(bool(x) for x in required_checks) / len(required_checks), 3),
            "factsWithSources": round(claims_with_sources / len(claims), 3) if claims else 0,
            "officialSourceRatio": round(official_sources / len(sources), 3) if sources else 0,
            "moduleCount": len(modules.get("modules", [])), "heroImageCount": len(media.get("heroImages", [])),
            "languageCount": len(facts.get("languages") or ["en", "es"]),
            "templateContractValid": not template_errors,
        },
        "cost": cost,
        "timing": {"llmSeconds": round(sum(float(c.get("elapsedSeconds") or 0) for c in calls if not c.get("cached")), 2)},
        "templateContract": template_report,
    }


def _cost_summary(calls: list[dict[str, Any]]) -> dict[str, Any]:
    uncached = [call for call in calls if not call.get("cached")]
    known = [float(call["costUsd"]) for call in uncached if isinstance(call.get("costUsd"), (int, float))]
    missing = [str(call.get("task") or "unknown") for call in uncached if not isinstance(call.get("costUsd"), (int, float))]
    known_total = round(sum(known), 6)
    return {
        "totalUsd": known_total if not missing else None,
        "knownUsd": known_total,
        "complete": not missing,
        "missingCostTasks": missing,
        "calls": calls,
    }
