#!/usr/bin/env python3
"""
Step 4: Topic-relevance QA (LLM-powered, mandatory pipeline stage).

Reads articles/en/*.mdx and asks the LLM whether each article's actual
subject matter is about the game (game_name), or whether it has drifted into
an unrelated real-world topic that happens to share similar wording (e.g. a
game class/mechanic/location name that collides with a real-world job title
or place). Generic — not specific to any one game or genre.

Off-topic articles are deleted (the English source, plus any existing
translated versions of the same slug), so `translate` never processes them.

This step always runs as part of `seoscout run` — there is no skip flag.
Skipping it means shipping unreviewed output, which defeats the purpose of
running it at all (see doc/文不对题问题记录.md for what unreviewed output
looks like in practice: ~36% of articles topically wrong despite passing
every structural check).
"""

import asyncio
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from string import Template

import aiohttp

from .core.config import Config
from .core.llm_client import LLMClient
from .core.utils import load_json, save_json, ensure_dir, extract_source_fields


QA_SYSTEM_PROMPT = (
    "You are a precise content-relevance reviewer for a fan wiki site. "
    "You only output the exact VERDICT/REASON format requested, no extra commentary."
)

VERDICT_RE = re.compile(r'^VERDICT:\s*(ON_TOPIC|OFF_TOPIC)\s*$', re.MULTILINE | re.IGNORECASE)
REASON_RE = re.compile(r'^REASON:\s*(.+)$', re.MULTILINE | re.IGNORECASE)


# ── helpers ─────────────────────────────────────────────────────

def load_prompt_template(prompt_path: str = None) -> str:
    """Load QA prompt template from file or built-in default.

    Template variables (string.Template $var syntax): $game_name, $title,
    $body — same "no leading comment inside the .md file" rationale as
    generate.py/translate.py/classify.py's load_prompt_template().
    """
    if prompt_path:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    default = Path(__file__).parent / "templates" / "qa.md"
    with open(default, 'r', encoding='utf-8') as f:
        return f.read()


def clean_llm_output(content: str) -> str:
    """Strip outer code fences, if any."""
    content = content.strip()
    if content.startswith('```'):
        first_newline = content.find('\n')
        content = content[first_newline + 1:] if first_newline != -1 else content[3:]
    if content.rstrip().endswith('```'):
        content = content.rstrip()[:-3].rstrip()
    return content


def _parse_verdict(content: str):
    """Returns (verdict, reason) or None if the response doesn't match the
    expected VERDICT:/REASON: shape — callers should treat None as
    inconclusive (keep the file, retry next run), never as OFF_TOPIC."""
    v_m = VERDICT_RE.search(content)
    if not v_m:
        return None
    r_m = REASON_RE.search(content)
    reason = r_m.group(1).strip() if r_m else ""
    return v_m.group(1).upper(), reason


def _log_removed(entry: dict):
    log_path = Path(Config.OUT_DIR) / "qa_removed.jsonl"
    ensure_dir(str(log_path.parent))
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _remove_article_and_translations(en_path: Path, en_dir: Path, rel: str, reason: str):
    """Delete the English article and any existing translated versions of the
    same relative path — a translation of now-removed source content must
    not survive as a stale orphan. Logs every removal for audit."""
    articles_root = en_dir.parent  # .../articles
    removed = []

    if en_path.exists():
        en_path.unlink()
        removed.append(str(en_path))

    if articles_root.exists():
        for lang_dir in articles_root.iterdir():
            if not lang_dir.is_dir() or lang_dir.name == 'en':
                continue
            candidate = lang_dir / rel
            if candidate.exists():
                candidate.unlink()
                removed.append(str(candidate))

    _log_removed({
        'slug': rel,
        'verdict': 'OFF_TOPIC',
        'reason': reason,
        'removed_files': removed,
        'removed_at': datetime.now().isoformat(),
    })


# ── main logic ──────────────────────────────────────────────────

async def run_qa(project: str, keywords_file: str, prompt_path: str = None, overwrite: bool = False):
    """Review generated English articles for topic relevance; delete off-topic ones."""
    Config.init(project)

    print("=" * 70)
    print(f"  Step 4: Topic QA [{project}]")
    print("=" * 70)

    # Read game_name (same pattern as search.py)
    game_name = ''
    try:
        kw_raw = load_json(keywords_file)
        game_name = str(kw_raw.get('game_name', '')).strip()
    except Exception:
        pass

    if not game_name:
        print("  ⚠️  No game_name found in keywords file — skipping topic QA\n")
        return

    en_dir = Path(Config.DATA_DIR) / "articles" / "en"
    if not en_dir.exists():
        print(f"  ❌ No English articles found at {en_dir}")
        print("     Run `seoscout generate` first")
        return

    articles = sorted(en_dir.glob("**/*.mdx"))
    if not articles:
        print("  ℹ️  No articles to review\n")
        return

    if not Config.LLM_API_KEYS:
        print("  ❌ LLM_API_KEY_1 (or LLM_API_KEY) not set — cannot run topic QA")
        return

    # Cache: {relative_path: {"verdict":..., "reason":..., "checked_at":...}}
    cache_path = f"{Config.OUT_DIR}/qa_results.json"
    fingerprints_path = f"{Config.OUT_DIR}/generation_fingerprints.json"
    fingerprints = load_json(fingerprints_path) if os.path.exists(fingerprints_path) else {}
    cache = {}
    if os.path.exists(cache_path) and not overwrite:
        try:
            cache = {str(key).replace('\\', '/'): value for key, value in load_json(cache_path).items()}
        except Exception:
            cache = {}

    prompt_template = Template(load_prompt_template(prompt_path))

    tasks_to_run = []
    kept_from_cache = 0
    for article_path in articles:
        rel = article_path.relative_to(en_dir).as_posix()
        try:
            source = extract_source_fields(article_path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as e:
            print(f"  ⚠️  Skipping {rel}: {e}")
            continue

        cached = cache.get(rel) or {}
        source_fingerprint = fingerprints.get(rel)
        if not overwrite and cached.get('verdict') == 'ON_TOPIC' and (
            not cached.get('source_fingerprint') or cached.get('source_fingerprint') == source_fingerprint
        ):
            if source_fingerprint and not cached.get('source_fingerprint'):
                cached['source_fingerprint'] = source_fingerprint
            kept_from_cache += 1
            continue
        if (
            not overwrite
            and source_fingerprint
            and cached.get('verdict') == 'OFF_TOPIC'
            and cached.get('source_fingerprint') == source_fingerprint
        ):
            _remove_article_and_translations(article_path, en_dir, rel, cached.get('reason', 'Cached off-topic verdict'))
            kept_from_cache += 1
            continue

        prompt = prompt_template.substitute(
            game_name=game_name,
            title=source['title'],
            body=source['body'],
        )
        tasks_to_run.append({'rel': rel, 'path': article_path, 'prompt': prompt, 'source_fingerprint': source_fingerprint})

    if kept_from_cache:
        print(f"  ✅ {kept_from_cache} article(s) already reviewed (cached) — pass --overwrite to re-review\n")

    if not tasks_to_run:
        print("  ℹ️  Nothing new to review\n")
        return

    print(f"  🔍 Reviewing {len(tasks_to_run)} article(s) for topic relevance...")
    print(f"     Model: {Config.LLM_MODEL}\n")

    client = LLMClient()
    client.stats['start_time'] = time.time()

    batch_size = Config.GENERATE_BATCH_SIZE
    on_topic = 0
    off_topic = 0
    inconclusive = 0

    async with aiohttp.ClientSession() as session:
        for i in range(0, len(tasks_to_run), batch_size):
            batch = tasks_to_run[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(tasks_to_run) + batch_size - 1) // batch_size
            print(f"  📦 Batch {batch_num}/{total_batches} ({len(batch)} articles)...")

            results = await asyncio.gather(*[
                client.generate_single(session, t['prompt'], {'keyword': t['rel']}, system=QA_SYSTEM_PROMPT)
                for t in batch
            ])

            for t, content in zip(batch, results):
                rel = t['rel']
                if not content:
                    print(f"    ⚠️  {rel}: no response, will retry next run")
                    inconclusive += 1
                    continue

                parsed = _parse_verdict(clean_llm_output(content))
                if not parsed:
                    print(f"    ⚠️  {rel}: unparseable response, will retry next run")
                    inconclusive += 1
                    continue

                verdict, reason = parsed
                cache[rel] = {
                    'verdict': verdict,
                    'reason': reason,
                    'checked_at': datetime.now().isoformat(),
                    'source_fingerprint': t.get('source_fingerprint'),
                }

                if verdict == 'ON_TOPIC':
                    on_topic += 1
                    print(f"    ✅ {rel}")
                else:
                    off_topic += 1
                    print(f"    🗑️  {rel} — {reason}")
                    _remove_article_and_translations(t['path'], en_dir, rel, reason)

    save_json(cache, cache_path)
    client.stats['end_time'] = time.time()

    print("\n" + "=" * 70)
    print("  ✅ Topic QA complete")
    print("=" * 70)
    print(f"  On-topic:     {on_topic}")
    print(f"  Off-topic:    {off_topic} (removed, incl. any existing translations)")
    if inconclusive:
        print(f"  Inconclusive: {inconclusive} (will retry next run)")
    client.print_stats()
    print("=" * 70)
