#!/usr/bin/env python3
"""
Step 0: Auto-classify keywords into categories (optional, LLM-powered).

Reads a flat "keywords" list + "category_options" from the keywords JSON,
asks the LLM to assign each keyword to one of the allowed categories,
outputs classified_keywords.json for review before running search.
"""

import asyncio
import json
import os
import time
from pathlib import Path
from string import Template

import aiohttp

from .core.config import Config
from .core.llm_client import LLMClient
from .core.utils import load_json, save_json, ensure_dir


CLASSIFY_SYSTEM_PROMPT = (
    "You are a precise data classification assistant. "
    "You only output valid JSON, with no extra commentary."
)


# ── helpers ─────────────────────────────────────────────────────

def _read_raw(keywords_file: str) -> dict:
    try:
        return load_json(keywords_file)
    except Exception:
        return {}


def should_auto_classify(keywords_file: str) -> bool:
    """True iff the input is a flat keyword list with non-empty category_options
    and no manual "categories" already provided."""
    data = _read_raw(keywords_file)

    categories = data.get("categories")
    if isinstance(categories, list) and any(
        isinstance(c, dict) and c.get("keywords") for c in categories
    ):
        return False

    options = data.get("category_options")
    if not isinstance(options, list) or not options:
        return False

    keywords = data.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        return False

    return True


def _read_classify_inputs(keywords_file: str):
    data = _read_raw(keywords_file)

    game_name = str(data.get("game_name", "")).strip()

    options = data.get("category_options", [])
    seen = {}
    for opt in options:
        if isinstance(opt, str) and opt.strip():
            key = opt.strip().lower()
            if key not in seen:
                seen[key] = opt.strip()
    category_options = list(seen.values())

    keyword_strings = []
    for kw in data.get("keywords", []):
        if isinstance(kw, str) and kw.strip():
            keyword_strings.append(kw.strip())

    return game_name, category_options, keyword_strings


def load_prompt_template(prompt_path: str = None) -> str:
    """Load classify prompt template from file or built-in default.

    Template variables (string.Template $var syntax): $game_name (game/
    product name for context), $category_options (JSON array of allowed
    category names), $keywords_json (JSON array of keyword strings to
    classify).

    Deliberately not documented as a leading comment inside the .md file
    itself — see generate.py's load_prompt_template() for why (that comment
    text becomes the literal first thing the model reads, and has been
    observed leaking into real output for the generate/translate templates).
    """
    if prompt_path:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    default = Path(__file__).parent / "templates" / "classify.md"
    with open(default, 'r', encoding='utf-8') as f:
        return f.read()


def clean_llm_output(content: str) -> str:
    """Strip code fences (handles any language tag like ```json, ```javascript)."""
    content = content.strip()
    if content.startswith('```'):
        first_newline = content.find('\n')
        if first_newline != -1:
            content = content[first_newline + 1:]
        else:
            content = content[3:]
    if content.rstrip().endswith('```'):
        content = content.rstrip()[:-3].rstrip()
    return content.strip()


def _parse_and_validate(raw_content: str, input_keywords, category_options):
    """
    Returns (valid_entries, problem_keywords, error_summary).
    valid_entries: list of {"keyword": ..., "category": ...} for successfully
                   classified keywords (category normalized to canonical casing).
    problem_keywords: keywords that are missing or have an invalid category.
    """
    options_by_lower = {c.lower(): c for c in category_options}
    input_set = set(input_keywords)

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as e:
        return [], list(input_keywords), f"JSON parse error: {e}"

    # Defensively unwrap a single list-valued wrapper dict.
    if isinstance(parsed, dict):
        list_values = [v for v in parsed.values() if isinstance(v, list)]
        if len(list_values) == 1:
            parsed = list_values[0]

    if not isinstance(parsed, list):
        return [], list(input_keywords), "Response is not a JSON array"

    by_keyword = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        kw = item.get("keyword")
        cat = item.get("category")
        if not isinstance(kw, str) or not isinstance(cat, str):
            continue
        kw = kw.strip()
        if kw not in input_set:
            continue
        canonical = options_by_lower.get(cat.strip().lower())
        if canonical is None:
            continue
        by_keyword[kw] = canonical

    valid_entries = []
    problems = []
    for kw in input_keywords:
        if kw in by_keyword:
            valid_entries.append({"keyword": kw, "category": by_keyword[kw]})
        else:
            problems.append(kw)

    err = "" if not problems else f"{len(problems)} keyword(s) missing or had an invalid category"
    return valid_entries, problems, err


def _build_repair_prompt(base_prompt: str, previous_output: str, problems, category_options) -> str:
    return (
        base_prompt
        + "\n\n---\n\n"
        f"The previous response had issues with these keywords (missing, or category "
        f"not exactly matching one of the allowed options):\n"
        f"{json.dumps(problems, ensure_ascii=False)}\n\n"
        f"Previous response (for reference, do NOT repeat the same mistakes):\n"
        f"{previous_output[:2000]}\n\n"
        f"Re-output the COMPLETE JSON array covering every keyword in the ORIGINAL keyword "
        f"list, including the ones listed above. Every category value must be copied "
        f"verbatim from: {json.dumps(category_options, ensure_ascii=False)}\n"
        f"Output ONLY the JSON array. Do NOT wrap it in code fences."
    )


# ── main logic ──────────────────────────────────────────────────

async def run_classify(project: str, keywords_file: str, prompt_path: str = None, overwrite: bool = False):
    """Auto-classify keywords into categories using the LLM, if opted in."""
    Config.init(project)

    print("=" * 70)
    print(f"  Step 0: Classify [{project}]")
    print("=" * 70)

    if not should_auto_classify(keywords_file):
        print("  ℹ️  No 'category_options' + flat 'keywords' found — nothing to classify\n")
        return

    game_name, category_options, keyword_strings = _read_classify_inputs(keywords_file)

    if not keyword_strings:
        print("  ❌ No keywords found")
        return

    if not category_options:
        print("  ⚠️  category_options is empty after cleanup — skipping auto-classify\n")
        return

    cache_path = f"{Config.OUT_DIR}/classified_keywords.json"
    if os.path.exists(cache_path) and not overwrite:
        cached = load_json(cache_path)
        print(f"  ✅ Already classified ({len(cached)} keywords) — {cache_path}")
        print("     Pass --overwrite to reclassify, or hand-edit the file and re-run search.\n")
        return

    if not Config.LLM_API_KEYS:
        print("  ❌ LLM_API_KEY_1 (or LLM_API_KEY) not set — cannot auto-classify")
        return

    print(f"  🏷️  Game: {game_name or '(unspecified)'}")
    print(f"  📂 Category options: {', '.join(category_options)}")
    print(f"  📋 Keywords to classify: {len(keyword_strings)}\n")

    prompt_template_str = load_prompt_template(prompt_path)
    prompt_template = Template(prompt_template_str)

    prompt = prompt_template.substitute(
        game_name=game_name or "(unspecified)",
        category_options=json.dumps(category_options, ensure_ascii=False),
        keywords_json=json.dumps(keyword_strings, indent=2, ensure_ascii=False),
    )

    client = LLMClient()
    ensure_dir(Config.OUT_DIR)

    client.stats['start_time'] = time.time()

    async with aiohttp.ClientSession() as session:
        raw = await client.generate_single(
            session, prompt,
            meta={'keyword': 'classify_batch'},
            system=CLASSIFY_SYSTEM_PROMPT,
        )

        if not raw:
            print("  ❌ LLM returned no response")
            return

        cleaned = clean_llm_output(raw)
        valid_entries, problems, err = _parse_and_validate(cleaned, keyword_strings, category_options)

        if problems:
            print(f"  ⚠️  {err} — attempting one repair pass...")
            repair_prompt = _build_repair_prompt(prompt, cleaned, problems, category_options)
            raw2 = await client.generate_single(
                session, repair_prompt,
                meta={'keyword': 'classify_repair'},
                system=CLASSIFY_SYSTEM_PROMPT,
            )
            if raw2:
                cleaned2 = clean_llm_output(raw2)
                valid_entries2, problems2, err2 = _parse_and_validate(cleaned2, problems, category_options)
                resolved_by_kw = {e['keyword']: e for e in valid_entries2}
                # Merge repaired entries back in, preserving original order.
                valid_by_kw = {e['keyword']: e for e in valid_entries}
                valid_by_kw.update(resolved_by_kw)
                still_missing = [kw for kw in problems if kw not in resolved_by_kw]

                valid_entries = [
                    valid_by_kw.get(kw, {"keyword": kw, "category": ""})
                    for kw in keyword_strings
                ]
                problems = still_missing

        if problems:
            print(f"  ⚠️  {len(problems)} keyword(s) still unresolved — falling back to uncategorized:")
            for kw in problems:
                print(f"     - {kw}")

    # valid_entries is already complete (every keyword present, fallback
    # category "" for unresolved ones) and in original keyword order.
    final_entries = valid_entries

    save_json(final_entries, cache_path)
    client.stats['end_time'] = time.time()

    counts = {}
    for e in final_entries:
        counts[e['category'] or '(uncategorized)'] = counts.get(e['category'] or '(uncategorized)', 0) + 1

    print("\n" + "=" * 70)
    print("  ✅ Classify complete")
    print("=" * 70)
    for cat, n in counts.items():
        print(f"  {cat}: {n}")
    print(f"  Output: {cache_path}")
    client.print_stats()
    print("\nNext steps:")
    print("  1. Review classified_keywords.json — hand-edit any category if needed")
    print(f"  2. Run: seoscout search --keywords {keywords_file}")
    print("=" * 70)
