from __future__ import annotations

import copy
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import Settings
from .http import CachedHttpClient
from .llm import LlmClient
from .media import build_assets
from .prompts import SYSTEM_JSON, homepage_prompt, localized_site_content_prompt, localized_site_content_revision_prompt, localized_value_revision_prompt, modules_prompt, research_prompt
from .report import render_basic_info
from .roblox import RobloxClient
from .schemas import DEFAULT_LANGUAGE_CODES, HOMEPAGE_SCHEMA, MODULES_SCHEMA, MONETIZATION_LANGUAGE_CODES, RESEARCH_SCHEMA, TEMPLATE_SITE_CONTENT_SCHEMA
from .template_contract import build_site_content, build_site_identity, publish_template_package, validate_localized_site_content, validate_template_contract
from .util import dump_json, load_json, safe_public_url, slugify, utc_now
from .validate import validate_package


class Pipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.http = CachedHttpClient(settings.cache_dir, timeout=45, refresh=settings.refresh)
        self.roblox = RobloxClient(self.http)
        self.llm = LlmClient(settings, self.http)

    def run(self, game_name: str) -> tuple[Path, dict[str, Any]]:
        started = time.monotonic()
        provisional_dir = self.settings.output_dir / slugify(game_name)
        previous_rejected: list[dict[str, Any]] = []
        previous_facts_path = provisional_dir / "facts.json"
        if previous_facts_path.exists():
            try:
                previous_rejected = load_json(previous_facts_path).get("identity", {}).get("rejectedCandidates", [])
            except (OSError, ValueError, TypeError):
                previous_rejected = []
        raw_dir = provisional_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        selected, candidates = self.roblox.select_identity(game_name)
        dump_json(raw_dir / "identity.json", {"query": game_name, "selected": selected, "candidates": candidates, "retrievedAt": utc_now()})
        facts, evidence, roblox_raw = self.roblox.collect(game_name, selected)
        current_rejected = facts.get("identity", {}).setdefault("rejectedCandidates", [])
        known_place_ids = {str(item.get("placeId")) for item in current_rejected}
        selected_place_id = str(facts.get("identity", {}).get("placeId"))
        for candidate in previous_rejected:
            place_id = str(candidate.get("placeId"))
            if place_id and place_id != selected_place_id and place_id not in known_place_ids:
                current_rejected.append(candidate)
                known_place_ids.add(place_id)
        output_dir = self.settings.output_dir / facts["identity"]["slug"]
        if output_dir != provisional_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            raw_dir = output_dir / "raw"
            raw_dir.mkdir(exist_ok=True)
            dump_json(raw_dir / "identity.json", {"query": game_name, "selected": selected, "candidates": candidates, "retrievedAt": utc_now()})
        dump_json(raw_dir / "roblox.json", roblox_raw)

        research, research_meta = self.llm.generate(
            "external_research", SYSTEM_JSON, research_prompt(_research_facts(facts)), RESEARCH_SCHEMA, web=True, ttl=7 * 86400
        )
        dump_json(raw_dir / "web-research.json", {"data": research, "meta": research_meta})
        facts, evidence = self._merge_research(facts, evidence, research)

        # Languages are a stable commercial policy.  Researching them for every
        # game costs more than translating the small homepage payload and made
        # the downstream contract unpredictable.
        facts = copy.deepcopy(facts)
        facts["languages"] = list(DEFAULT_LANGUAGE_CODES)
        facts["languageMarket"] = {
            "policy": "fixed-developed-markets-v1",
            "consideredCodes": list(DEFAULT_LANGUAGE_CODES),
            "selectedCodes": list(DEFAULT_LANGUAGE_CODES),
            "candidates": [],
            "notes": ["Fixed product policy; no per-game language-market API call."],
            "partial": False,
            "retrievedAt": utc_now(),
        }
        dump_json(raw_dir / "language-policy.json", facts["languageMarket"])

        media, palette = build_assets(facts, output_dir / "assets")
        generation_facts = _generation_facts(facts)
        generation_evidence = _generation_evidence(evidence)
        homepage, homepage_meta = self.llm.generate(
            "homepage_config", SYSTEM_JSON, homepage_prompt(generation_facts, generation_evidence, palette), HOMEPAGE_SCHEMA, web=False, ttl=30 * 86400
        )
        generated_languages = copy.deepcopy(homepage.get("languages", []))
        homepage["languages"] = _homepage_languages(facts)
        dump_json(raw_dir / "homepage-generation.json", {"data": homepage, "meta": homepage_meta, "generatedLanguages": generated_languages, "languageNormalization": "Replaced with fixed product language policy."})
        generated_modules, modules_meta = self.llm.generate(
            "homepage_modules", SYSTEM_JSON, modules_prompt(_module_facts(generation_facts), generation_evidence), MODULES_SCHEMA, web=True, ttl=7 * 86400
        )
        modules, normalizations = _normalize_modules(generated_modules)
        modules["modules"] = sorted(modules["modules"], key=lambda item: item["order"])
        dump_json(raw_dir / "module-research.json", {"data": generated_modules, "meta": modules_meta, "normalizations": normalizations})
        # Do not replace the last successful facts/evidence if a downstream LLM task fails.
        dump_json(output_dir / "facts.json", facts)
        dump_json(output_dir / "evidence.json", evidence)

        site_identity = build_site_identity(facts)
        site_content = build_site_content(facts, homepage)
        localized_contents: dict[str, dict[str, Any]] = {}
        language_names = {item.get("code"): item.get("language") for item in homepage.get("languages", [])}
        for locale in site_identity.get("LANGUAGES", []):
            if locale == "en":
                continue
            localized, localized_meta = self.llm.generate(
                f"homepage_locale_{locale}",
                SYSTEM_JSON,
                localized_site_content_prompt(
                    locale,
                    language_names.get(locale) or locale,
                    site_identity["GAME_NAME"],
                    site_content,
                ),
                TEMPLATE_SITE_CONTENT_SCHEMA,
                web=False,
                ttl=30 * 86400,
            )
            locale_errors = validate_localized_site_content(localized, site_content, locale, facts)
            revision_meta = None
            rejected_draft = None
            if locale_errors:
                rejected_draft = localized
                localized, revision_meta = self.llm.generate(
                    f"homepage_locale_{locale}_revision",
                    SYSTEM_JSON,
                    localized_site_content_revision_prompt(
                        locale,
                        language_names.get(locale) or locale,
                        site_identity["GAME_NAME"],
                        site_content,
                        rejected_draft,
                        locale_errors,
                    ),
                    TEMPLATE_SITE_CONTENT_SCHEMA,
                    web=False,
                    ttl=30 * 86400,
                )
            remaining_errors = validate_localized_site_content(localized, site_content, locale, facts)
            value_revision_meta = None
            value_revision = None
            repairable = [error for error in remaining_errors if error.get("code") == "TEMPLATE_LOCALE_FACT_MISMATCH"]
            if repairable and len(repairable) == len(remaining_errors):
                corrections: dict[str, dict[str, str]] = {}
                prefix = f"site-content.{locale}."
                for error in repairable:
                    path = error["field"].removeprefix(prefix)
                    corrections[path] = {
                        "englishValue": str(_path_value(site_content, path) or ""),
                        "currentValue": str(_path_value(localized, path) or ""),
                        "error": error["message"],
                        "constraint": "80-180 characters" if path in {"site.description", "home.meta.description"} else "Match the production schema.",
                    }
                correction_schema = {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["values"],
                    "properties": {
                        "values": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": list(corrections),
                            "properties": {
                                path: _localized_correction_schema(path, details["englishValue"], locale)
                                for path, details in corrections.items()
                            },
                        }
                    },
                }
                value_revision, value_revision_meta = self.llm.generate(
                    f"homepage_locale_{locale}_value_revision",
                    SYSTEM_JSON,
                    localized_value_revision_prompt(locale, language_names.get(locale) or locale, corrections),
                    correction_schema,
                    web=False,
                    ttl=30 * 86400,
                )
                localized = copy.deepcopy(localized)
                for path, value in value_revision["values"].items():
                    _set_path_value(localized, path, value)
            localized_contents[locale] = localized
            dump_json(raw_dir / f"site-content.{locale}-generation.json", {
                "data": localized,
                "meta": revision_meta or localized_meta,
                "initialMeta": localized_meta,
                "rejectedDraft": rejected_draft,
                "initialValidationErrors": locale_errors,
                "valueRevision": value_revision,
                "valueRevisionMeta": value_revision_meta,
            })
        template_report = validate_template_contract(site_identity, site_content, facts, output_dir, localized_contents)
        publish_template_package(output_dir, site_identity, site_content, template_report, localized_contents)
        validation = validate_package(
            facts, evidence, homepage, modules, media, self.llm.calls,
            site_identity, site_content, output_dir, localized_contents,
        )
        validation["timing"]["totalSeconds"] = round(time.monotonic() - started, 2)
        dump_json(output_dir / "00首页信息.json", homepage)
        dump_json(output_dir / "00首页模块.json", modules)
        dump_json(output_dir / "validation-report.json", validation)
        dump_json(output_dir / "template-validation-report.json", validation["templateContract"])
        (output_dir / "00基础信息.md").write_text(
            render_basic_info(facts, evidence, homepage, validation), encoding="utf-8"
        )
        return output_dir, validation

    def _merge_research(self, facts: dict[str, Any], evidence: dict[str, Any], research: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        facts = copy.deepcopy(facts)
        evidence = copy.deepcopy(evidence)
        retrieved = utc_now()
        valid_cache: dict[str, tuple[bool, int | None]] = {}

        def valid(url: str | None) -> bool:
            if not url or not safe_public_url(url):
                return False
            if url in valid_cache:
                return valid_cache[url][0]
            try:
                response = self.http.get(url, ttl=604800)
                ok = response.status_code not in {404, 410} and response.status_code < 500
                valid_cache[url] = (ok, response.status_code)
            except Exception:
                valid_cache[url] = (False, None)
            return valid_cache[url][0]

        external_urls: dict[str, str] = {}
        for key, url in research.get("officialLinks", {}).items():
            if valid(url):
                facts["officialLinks"][key] = url
                external_urls[url] = "official-social" if _is_social(url) else "official-creator"
        trailer = research.get("trailer")
        if valid(trailer):
            facts["officialLinks"]["trailer"] = trailer
            external_urls[trailer] = "official-social"
        facts["codes"] = []
        for code in research.get("codes", []):
            urls = [url for url in code.get("sourceUrls", []) if valid(url)]
            if not urls:
                continue
            item = {**code, "sourceUrls": urls, "retrievedAt": retrieved}
            facts["codes"].append(item)
            for url in urls:
                external_urls.setdefault(url, "third-party")
        facts["gameplayFacts"] = []
        for fact in research.get("gameplayFacts", []):
            urls = [url for url in fact.get("sourceUrls", []) if valid(url)]
            if urls or fact.get("confidence", 0) < 0.6:
                facts["gameplayFacts"].append({**fact, "sourceUrls": urls})
            for url in urls:
                external_urls.setdefault(url, "official-social" if _is_social(url) else "third-party")
        facts["languageSignals"] = []
        for signal in research.get("languageSignals", []):
            urls = [url for url in signal.get("sourceUrls", []) if valid(url)]
            facts["languageSignals"].append({**signal, "sourceUrls": urls})
            for url in urls:
                external_urls.setdefault(url, "third-party")
        source_by_url = {source["url"]: source["id"] for source in evidence["sources"]}
        for index, (url, source_type) in enumerate(external_urls.items(), 1):
            if url in source_by_url:
                continue
            source_id = f"src_web_{index}"
            source_by_url[url] = source_id
            evidence["sources"].append({
                "id": source_id, "url": url, "title": urlparse(url).netloc,
                "sourceType": source_type, "publisher": urlparse(url).netloc,
                "retrievedAt": retrieved, "httpStatus": valid_cache.get(url, (True, None))[1], "accessible": True,
            })
        for key, url in facts["officialLinks"].items():
            if url and url in source_by_url:
                evidence["claims"].append({"field": f"officialLinks.{key}", "sourceIds": [source_by_url[url]], "confidence": 0.9, "classification": "fact"})
        for index, code in enumerate(facts["codes"]):
            evidence["claims"].append({"field": f"codes.{index}", "sourceIds": [source_by_url[url] for url in code["sourceUrls"] if url in source_by_url], "confidence": 0.95 if code["officiallyVerified"] else 0.65, "classification": "fact"})
        facts["researchNotes"] = research.get("notes", [])
        existing_rejected = facts["identity"].get("rejectedCandidates", [])
        creator_rejected = self._creator_link_candidates(
            facts["officialLinks"].get("website"), facts["identity"]["placeId"]
        )
        merged_rejected: list[dict[str, Any]] = []
        seen_place_ids: set[str] = set()
        for candidate in [*existing_rejected, *creator_rejected]:
            place_id = str(candidate.get("placeId", ""))
            if place_id and place_id not in seen_place_ids:
                merged_rejected.append(candidate)
                seen_place_ids.add(place_id)
        facts["identity"]["rejectedCandidates"] = merged_rejected
        return facts, evidence

    def _merge_language_market(self, facts: dict[str, Any], evidence: dict[str, Any], research: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        facts = copy.deepcopy(facts)
        evidence = copy.deepcopy(evidence)
        retrieved = utc_now()
        valid_cache: dict[str, tuple[bool, int | None]] = {}

        def valid(url: str) -> bool:
            if not safe_public_url(url):
                return False
            host = (urlparse(url).hostname or "").lower()
            if any(host == domain or host.endswith("." + domain) for domain in ("fandom.com", "wiki.gg", "fextralife.com")):
                return False
            if url in valid_cache:
                return valid_cache[url][0]
            try:
                response = self.http.get(url, ttl=14 * 86400)
                ok = response.status_code not in {404, 410} and response.status_code < 500
                valid_cache[url] = (ok, response.status_code)
            except Exception:
                valid_cache[url] = (False, None)
            return valid_cache[url][0]

        normalized: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        for candidate in research.get("candidates", []):
            code = str(candidate.get("code", "")).lower()
            if code not in MONETIZATION_LANGUAGE_CODES or code in seen_codes:
                continue
            seen_codes.add(code)
            signals: list[dict[str, Any]] = []
            for signal in candidate.get("signals", []):
                urls = [url for url in dict.fromkeys(signal.get("sourceUrls", [])) if valid(url)]
                if urls:
                    signals.append({**signal, "sourceUrls": urls})
            source_urls = list(dict.fromkeys(url for signal in signals for url in signal["sourceUrls"]))
            normalized.append({**candidate, "code": code, "signals": signals, "sourceUrls": source_urls})

        missing_codes = [code for code in MONETIZATION_LANGUAGE_CODES if code not in seen_codes]
        selected_codes = _select_language_codes(normalized)
        notes = list(research.get("notes", []))
        if missing_codes:
            notes.append("Language task omitted required monetization-scope candidates: " + ", ".join(missing_codes))
        facts["languages"] = selected_codes
        facts["languageMarket"] = {
            "policy": "seo-ad-revenue-v1",
            "consideredCodes": list(MONETIZATION_LANGUAGE_CODES),
            "selectedCodes": selected_codes,
            "candidates": normalized,
            "notes": notes,
            "partial": bool(research.get("partial")) or bool(missing_codes),
            "retrievedAt": retrieved,
        }

        source_by_url = {source["url"]: source["id"] for source in evidence.get("sources", [])}
        next_index = 1
        for candidate in normalized:
            if candidate["code"] not in selected_codes:
                continue
            ids: list[str] = []
            for url in candidate["sourceUrls"]:
                if url not in source_by_url:
                    while f"src_language_{next_index}" in source_by_url.values():
                        next_index += 1
                    source_id = f"src_language_{next_index}"
                    next_index += 1
                    source_by_url[url] = source_id
                    evidence.setdefault("sources", []).append({
                        "id": source_id,
                        "url": url,
                        "title": urlparse(url).netloc,
                        "sourceType": "official-social" if _is_social(url) else "third-party",
                        "publisher": urlparse(url).netloc,
                        "retrievedAt": retrieved,
                        "httpStatus": valid_cache.get(url, (True, None))[1],
                        "accessible": True,
                    })
                ids.append(source_by_url[url])
            evidence.setdefault("claims", []).append({
                "field": f"languages.{candidate['code']}",
                "sourceIds": ids,
                "confidence": candidate.get("confidence", 0),
                "classification": "recommendation",
            })
        return facts, evidence

    def _creator_link_candidates(self, website: str | None, selected_place_id: str) -> list[dict[str, str]]:
        if not website:
            return []
        try:
            reader_url = "https://r.jina.ai/" + website
            response = self.http.get(reader_url, ttl=604800)
            if response.status_code >= 400:
                return []
            results: list[dict[str, str]] = []
            seen: set[str] = set()
            for match in re.finditer(r"https?://(?:www\.)?roblox\.com/games/(\d+)(?:/[^\s)\]]*)?", response.text, re.I):
                place_id = match.group(1)
                if place_id == selected_place_id or place_id in seen:
                    continue
                seen.add(place_id)
                results.append({
                    "placeId": place_id,
                    "url": match.group(0),
                    "reason": "Creator-owned hub links to a different Place; current Roblox Discover and API identity was retained.",
                })
            return results
        except Exception:
            return []


def _is_social(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(domain in host for domain in ["discord.com", "discord.gg", "youtube.com", "youtu.be", "x.com", "twitter.com", "tiktok.com", "reddit.com"])


def _path_value(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def _set_path_value(value: Any, path: str, replacement: str) -> None:
    parts = path.split(".")
    current = value
    for part in parts[:-1]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    last = parts[-1]
    if isinstance(current, list):
        current[int(last)] = replacement
    else:
        current[last] = replacement


def _localized_correction_schema(path: str, english_value: str, locale: str) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if path in {"site.description", "home.meta.description"}:
        schema.update({"minLength": 80, "maxLength": 180})
    numeric_tokens = list(dict.fromkeys(re.findall(r"\d+(?:\.\d+)?", english_value)))
    patterns: list[str] = []
    if numeric_tokens:
        patterns.append(r"^\D*" + r"\D*".join(re.escape(token) for token in numeric_tokens) + r"\D*$")
    if locale == "es":
        anchors = {
            "players": "jugador",
            "units": "unidad",
            "level": "nivel",
            "evolve": "evol",
            "team up": "equipo|coopera",
        }
        lowered = english_value.casefold()
        patterns.extend(pattern for source, pattern in anchors.items() if re.search(rf"\b{re.escape(source)}\b", lowered))
    if patterns:
        schema["allOf"] = [{"pattern": pattern} for pattern in dict.fromkeys(patterns)]
    return schema


def _normalize_modules(value: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    result = copy.deepcopy(value)
    changes: list[dict[str, str]] = []
    for module in result.get("modules", []):
        name = module.get("name", "").casefold()
        old = module.get("displayType")
        new = old
        if old == "code-cards" and "code" not in name:
            new = "card-list"
        elif old == "tier-grid" and not any(word in name for word in ("tier", "rank")):
            new = "card-list"
        if new != old:
            module["displayType"] = new
            changes.append({"module": module.get("name", ""), "from": old, "to": new, "reason": "Display type did not match module semantics."})
    return result, changes


def _generation_facts(facts: dict[str, Any]) -> dict[str, Any]:
    """Exclude audit-only fields so they do not invalidate content-generation caches."""
    result = copy.deepcopy(facts)
    result.get("identity", {}).pop("rejectedCandidates", None)
    result.pop("researchNotes", None)
    _remove_timestamps(result)
    return result


def _research_facts(facts: dict[str, Any]) -> dict[str, Any]:
    """Provide identity/context to web research without volatile stats or media URLs."""
    return {
        "identity": copy.deepcopy(facts.get("identity", {})),
        "developer": copy.deepcopy(facts.get("developer", {})),
        "game": copy.deepcopy(facts.get("game", {})),
        "officialLinks": {
            "roblox": facts.get("officialLinks", {}).get("roblox"),
            "robloxGroup": facts.get("officialLinks", {}).get("robloxGroup"),
        },
    }


def _language_research_facts(facts: dict[str, Any]) -> dict[str, Any]:
    """Keep language-market research focused on identity, official surfaces and prior language clues."""
    return {
        "identity": {
            key: facts.get("identity", {}).get(key)
            for key in ("canonicalName", "canonicalUrl", "placeId", "universeId")
        },
        "developer": copy.deepcopy(facts.get("developer", {})),
        "officialDescription": facts.get("game", {}).get("officialDescription", ""),
        "officialLinks": copy.deepcopy(facts.get("officialLinks", {})),
        "initialLanguageSignals": copy.deepcopy(facts.get("languageSignals", [])),
    }


def _select_language_codes(candidates: list[dict[str, Any]]) -> list[str]:
    """Select at most four languages with reproducible evidence thresholds; English is the fallback."""
    eligible: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.get("recommendation") != "include" or float(candidate.get("confidence") or 0) < 0.7:
            continue
        signals = candidate.get("signals", [])
        source_urls = candidate.get("sourceUrls", [])
        publishers = {str(signal.get("publisher", "")).strip().casefold() for signal in signals if signal.get("publisher")}
        hosts = {(urlparse(url).hostname or "").lower() for url in source_urls}
        independent_sources = max(len(publishers), len(hosts))
        creator_official_support = any(
            signal.get("signalType") == "official-localization"
            and str(signal.get("publisher", "")).strip().casefold() not in {"roblox", "roblox corporation", "roblox platform"}
            and signal.get("sourceUrls")
            for signal in signals
        )
        if candidate.get("code") == "en" or (candidate.get("officialSupport") and creator_official_support) or (len(source_urls) >= 2 and independent_sources >= 2):
            eligible.append(candidate)
    eligible.sort(key=lambda item: (-float(item.get("confidence") or 0), str(item.get("code"))))
    selected = list(DEFAULT_LANGUAGE_CODES)
    for candidate in eligible:
        code = candidate.get("code")
        if code in MONETIZATION_LANGUAGE_CODES and code not in selected:
            selected.append(code)
        if len(selected) == 4:
            break
    return selected


def _homepage_languages(facts: dict[str, Any]) -> list[dict[str, Any]]:
    name = facts.get("identity", {}).get("canonicalName", "")
    candidates = {
        candidate.get("code"): candidate
        for candidate in facts.get("languageMarket", {}).get("candidates", [])
    }
    language_names = {
        "en": "English",
        "es": "Spanish",
        "de": "German",
        "fr": "French",
        "ja": "Japanese",
        "ko": "Korean",
    }
    result: list[dict[str, Any]] = []
    for rank, code in enumerate(facts.get("languages") or DEFAULT_LANGUAGE_CODES, 1):
        candidate = candidates.get(code, {})
        source_urls = candidate.get("sourceUrls", [])
        result.append({
            "rank": rank,
            "code": code,
            "language": candidate.get("language") or language_names.get(code, code),
            "localizedSiteName": f"{name} Wiki",
            "gameName": name,
            "basis": "evidence" if source_urls else "policy",
            "sourceUrls": source_urls,
            "confidence": float(candidate.get("confidence") or 1.0),
        })
    return result


def _generation_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(evidence)
    _remove_timestamps(result)
    return result


def _module_facts(facts: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(facts)
    result.pop("dynamicStats", None)
    result.pop("media", None)
    return result


def _remove_timestamps(value: Any) -> None:
    if isinstance(value, dict):
        for key in list(value):
            if key in {"retrievedAt", "collectedAt", "verifiedAt"}:
                value.pop(key, None)
            else:
                _remove_timestamps(value[key])
    elif isinstance(value, list):
        for child in value:
            _remove_timestamps(child)
