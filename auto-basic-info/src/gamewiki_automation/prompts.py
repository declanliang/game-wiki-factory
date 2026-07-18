from __future__ import annotations

import json
from typing import Any

from .util import utc_now


SYSTEM_JSON = """You are a meticulous game research and website configuration system. Return only JSON matching the supplied schema. Never invent URLs, codes, dates, counts, mechanics, or community consensus. Missing information must be null or omitted only where the schema permits it. Roblox API facts supplied by the user are authoritative and must not be changed."""


def research_prompt(facts: dict[str, Any]) -> str:
    return f"""Research external official resources for this Roblox game as of {utc_now()[:10]}.

Authoritative Roblox facts:
{json.dumps(facts, ensure_ascii=False, indent=2)}

Find only these missing fields:
1. Creator-owned website or Linktree and official Discord, Reddit, YouTube, X and TikTok.
2. An official trailer or official gameplay video. Do not substitute a random popular video.
3. Redeem codes, with reward, status, official verification and every supporting URL. Third-party-only codes must be claimed-active or unknown, never verified-active.
4. Concise gameplay facts useful for homepage stats or guides, each with sources.
5. Language demand signals. English must be considered, Chinese must not be recommended. Do not claim country popularity without evidence.
6. Return moduleIdeas as an empty array in this task; module research runs separately.

Rules:
- Prefer Roblox, the developer's owned pages, official social accounts, official video descriptions and official announcements.
- Do not use competitor wiki, Fandom, wiki.gg, fextralife or generic aggregation pages as proof or frontend references.
- A URL must have appeared in an actual search result/page. Never construct a social URL from an assumed username.
- Do not re-research or change Place ID, Universe ID, creator, visits, favorites or player count.
- Set partial=true if important requested areas remain unresolved.
    """


def language_market_prompt(facts: dict[str, Any]) -> str:
    return f"""Research the language-market demand for this specific Roblox game as of {utc_now()[:10]}.

VERIFIED GAME CONTEXT:
{json.dumps(facts, ensure_ascii=False, indent=2)}

This is a dedicated SEO advertising-revenue language decision task, not a check of the official page language alone. Candidate scope is intentionally limited to markets prioritized by the site owner; do not spend searches on languages outside it.

Required investigation:
1. Return exactly one candidate for each of these codes, and no others: en, es, de, fr, ja, ko, it, nl.
2. English and Spanish are business-policy defaults. Still research their evidence, but recommendation must be include.
3. Search in each candidate language using the exact game name plus native-language terms for wiki, guide, codes, tier list or gameplay.
4. Look for game-specific official localization, creator communities, sustained native-language YouTube coverage, regional editorial coverage, or other direct demand signals.
5. Return include or exclude for every listed candidate so the audit proves the full allowed scope was checked.
6. Keep only the 1-3 strongest signals for each candidate language.

Decision rules:
- English and Spanish are always included as the monetization/coverage fallback. Other candidates must pass the evidence threshold.
- Recommend include only when there is official localized support, or at least two independent game-specific sources from different publishers/domains.
- A localized Roblox website route such as /pt/games/... only localizes Roblox's interface; it is not proof that the game itself has official localization or demand. Do not set officialSupport=true from that alone.
- A single page, generic Roblox/anime popularity, search snippets without accessible pages, duplicated syndication, or obvious machine-translated SEO spam is insufficient.
- Do not infer popularity from a country name, a creator name, or the existence of a language on Roblox.
- sourceUrls must be pages actually found during this task. Never invent or construct URLs.
- Never investigate or recommend Chinese. Do not investigate Portuguese, Vietnamese, Filipino/Tagalog, Russian, Turkish, Indonesian, Thai, Arabic, Polish or other out-of-scope languages even if some organic discussion exists; the business policy prioritizes higher-value ad markets.
- Keep the final recommended scope practical: no more than 4 included languages total, ranked implicitly by confidence; all non-default candidates that lack strong evidence should be exclude.
- Set partial=true if major candidate markets could not be meaningfully checked.
"""


def homepage_prompt(facts: dict[str, Any], evidence: dict[str, Any], palette: list[str]) -> str:
    return f"""Generate the English homepage configuration for a fan-made wiki using only the supplied facts and evidence.

FACTS:
{json.dumps(facts, ensure_ascii=False, indent=2)}

EVIDENCE:
{json.dumps(evidence, ensure_ascii=False, indent=2)}

Official icon color candidates (HSL): {json.dumps(palette)}

Requirements:
- Preserve the exact game name and URLs from FACTS.
- Both descriptions must be 140-160 Unicode characters. Both titles must be at most 60 characters. Keywords at most 100 characters.
- Hero stats: exactly 5 plain strings, no zero values; at most 2 dynamic stats. Favor launch/update, visits/players, server size, approval and sourced gameplay scale.
- Exactly 4 distinct Start cards; first is Beginner Guide.
- About stats: 5-7 entries including Developer, Platform and Genre. Never add unknown level caps or content counts.
- Sidebar always has 2 entries. Show real verified codes as Active; third-party supported codes as Unverified; fill remaining slots with code='Unavailable', reward='No verified active code found', status='Unavailable'.
- English is language rank 1. Output 1-4 languages total, exclude Chinese, do not translate the brand name. Unsupported languages are low-confidence inference.
- CTA play link must be the canonical Roblox URL. Other link fields are copied from facts or null.
- Light and dark theme colors should use the icon palette when suitable and be distinct.
- faviconPrompt describes a centered, simple, no-text 512x512 PNG icon inspired by the game's verified visual identity; do not copy third-party logos.
- Do not add claims that are absent from FACTS/EVIDENCE.
"""


def localized_site_content_prompt(locale: str, language: str, game_name: str, english_content: dict[str, Any]) -> str:
    return f"""Rewrite the supplied English game-wiki homepage content as publication-ready {language} ({locale}).

CANONICAL GAME NAME (preserve exactly; do not translate unless the source already contains an official localized name):
{game_name}

ENGLISH SOURCE JSON:
{json.dumps(english_content, ensure_ascii=False, indent=2)}

Requirements:
- Return exactly the same object keys, array lengths, array order, and value types as the English source.
- Rewrite every reader-facing string naturally for native {language} readers. This must read like original {language} web copy, not a literal or awkward translation.
- Preserve every source clause and all facts, numbers, dates, code strings, developer names, platform names, and the canonical game name. Do not summarize, add, or remove claims.
- Respect the production limits: site.description and home.meta.description must each be 80-180 characters; home.meta.title must be 10-60 characters. Compress wording, not facts, when the target language expands.
- Keep all other localized strings within the min/max lengths encoded in the supplied JSON Schema.
- For Spanish, prefer established game phrasing such as "unidades invocadas", "subir de nivel", "jugar en equipo" and "jugadores por servidor"; avoid literal calques such as "los invocados", "júntate en modos" or "servidores de jugadores".
- Values whose key is href, ends in Href, or is category are immutable identifiers: copy them byte-for-byte.
- Do not translate URLs, route paths, category identifiers, redeem codes, or brand/proper names such as Roblox.
- Keep Markdown ** emphasis and internal-link syntax intact while translating visible link text.
- Do not leave English prose in the result. Proper names and immutable identifiers are the only expected English-looking values.
- Return JSON only and match the supplied schema exactly.
"""


def localized_site_content_revision_prompt(
    locale: str,
    language: str,
    game_name: str,
    english_content: dict[str, Any],
    draft: dict[str, Any],
    errors: list[dict[str, str]],
) -> str:
    return f"""Correct a rejected {language} ({locale}) homepage localization.

CANONICAL GAME NAME: {game_name}

AUTHORITATIVE ENGLISH SOURCE:
{json.dumps(english_content, ensure_ascii=False, indent=2)}

REJECTED LOCALIZED DRAFT:
{json.dumps(draft, ensure_ascii=False, indent=2)}

VALIDATION ERRORS:
{json.dumps(errors, ensure_ascii=False, indent=2)}

Return one corrected JSON object. Keep the exact source key tree, arrays, order, facts, numbers, dates, names, code strings, href values, *Href values, and category values. Fix every listed error while retaining natural native {language} prose. Do not summarize or omit any source clause, and do not add claims.
"""


def localized_value_revision_prompt(
    locale: str,
    language: str,
    corrections: dict[str, dict[str, str]],
) -> str:
    return f"""Correct only the listed rejected strings in a {language} ({locale}) homepage localization.

FIELDS:
{json.dumps(corrections, ensure_ascii=False, indent=2)}

For each exact path, return one replacement string that expresses every clause and numeric fact from englishValue in natural native {language}. Fix the stated validation error, preserve proper names and numbers, and obey any length constraint described in the error. Do not return or modify any other field.
Prefer concise idiomatic grammar over telegraphic wording. For Spanish, use natural constructions such as "unidades invocadas luchan solas", "subir de nivel", "jugar en equipo" and "hasta 20 jugadores"; avoid unnatural shortcuts such as "autopelean" or dropping required articles and prepositions to save characters.
"""


def modules_prompt(facts: dict[str, Any], evidence: dict[str, Any]) -> str:
    return f"""Create 4-8 English homepage Explore modules for this Roblox game. Research only when the supplied facts do not contain enough detail.

FACTS:
{json.dumps(facts, ensure_ascii=False, indent=2)}

EVIDENCE:
{json.dumps(evidence, ensure_ascii=False, indent=2)}

Rules:
- Rank modules by real player usefulness and search intent; do not force 8.
- Module names start with the canonical game name.
- displayType is exactly code-cards, step-by-step, tier-grid, or card-list.
- Each module has 2-4 useful highlights and at least one real accessible reference.
- References must not include competitor sites, Fandom, wiki.gg, fextralife, or aggregation wikis. Prefer Roblox, creator-owned pages, official social pages/videos and authoritative platform documentation.
- Codes module may honestly say no verified code exists. Never invent codes.
- Tier lists are allowed only with versioned, cited evidence; otherwise omit them or mark editorial-draft and clearly phrase details as topics to evaluate, not rankings.
- Generic beginner steps may be editorial-draft, but specific mechanics/items must be supported by the facts or references.
- Orders are unique and contiguous from 1.
"""
