#!/usr/bin/env python3
"""
Step 3: Generate articles from collected material.

Reads collected/*.json (output from collect step), sends to LLM,
outputs MDX articles (JS export metadata) to articles/en/.
"""

import asyncio
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

from .core.config import Config
from .core.llm_client import LLMClient
from .core.utils import load_json, save_json, ensure_dir


# ── helpers ─────────────────────────────────────────────────────

def keyword_to_slug(keyword: str) -> str:
    """'My Game beginner guide' → 'my-game-beginner-guide'"""
    return re.sub(r'[^a-z0-9-]', '', keyword.lower().replace(' ', '-'))


def keyword_to_filename(keyword: str) -> str:
    """'My Game beginner guide' → 'my_game_beginner_guide'"""
    return re.sub(r'[^a-z0-9_]', '', keyword.lower().replace(' ', '_'))


def load_prompt_template(prompt_path: str = None) -> str:
    """Load prompt template from file or use built-in default.

    Template variables (str.format() {var} syntax): {merged_data} (collected
    reference material — JSON of YouTube transcripts + web content),
    {current_date} (YYYY-MM-DD), {category} (content category slug).

    Deliberately not documented as a leading comment inside the .md file
    itself — that comment becomes the literal first thing in the prompt sent
    to the model, and HTML/comment-shaped text there has been observed to
    get echoed into real output.
    """
    if prompt_path:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()

    # Built-in default
    default = Path(__file__).parent / "templates" / "generate.md"
    with open(default, 'r', encoding='utf-8') as f:
        return f.read()


def clean_llm_output(content: str) -> str:
    """Strip outer code fences and trim."""
    content = content.strip()
    if content.startswith('```markdown'):
        content = content[len('```markdown'):].lstrip('\n')
    elif content.startswith('```md'):
        content = content[len('```md'):].lstrip('\n')
    elif content.startswith('```'):
        content = content[3:].lstrip('\n')
    if content.rstrip().endswith('```'):
        content = content.rstrip()[:-3].rstrip()
    return content


# ── output parsing/assembly ─────────────────────────────────────
#
# The model is only asked to supply TITLE / DESCRIPTION / body (see
# templates/generate.md's Output Format section) — it never writes the
# `export const metadata = {...}` JS block itself. That block is always
# assembled by this code from known-good values (title/description via
# json.dumps() for correct escaping; category/date are already known, not
# LLM output). This eliminates a whole class of formatting failures that
# used to come from trusting the model to hand-write valid JS syntax: stray
# fence markers imitated from a format example, duplicated metadata blocks,
# unescaped quotes in title/description breaking the object literal, etc.

TITLE_RE = re.compile(r'^TITLE:\s*(.+)$', re.MULTILINE)
DESCRIPTION_RE = re.compile(r'^DESCRIPTION:\s*(.+)$', re.MULTILINE)
QUICKGUIDE_RE = re.compile(r'^QUICKGUIDE:[ \t]*\n', re.MULTILINE)
BODY_DELIM_RE = re.compile(r'^BODY:[ \t]*\n', re.MULTILINE)
BULLET_PREFIX_RE = re.compile(r'^[-*•]\s*')


def _parse_llm_output(content: str) -> tuple:
    """Parse the model's TITLE:/DESCRIPTION:/QUICKGUIDE:/BODY: contract.

    QUICKGUIDE is optional — a Quick Guide summary box is only rendered if
    present (see _build_mdx()), so its absence is not a validation failure.

    Returns (title, description, quickguide, body), where quickguide is a
    list of plain bullet strings (possibly empty). Raises ValueError with a
    human-readable reason if the expected shape isn't found — the caller
    routes that into the repair/regenerate pass, same as a validation
    failure.
    """
    title_m = TITLE_RE.search(content)
    if not title_m:
        raise ValueError("No 'TITLE:' line found in response")

    desc_m = DESCRIPTION_RE.search(content, title_m.end())
    if not desc_m:
        raise ValueError("No 'DESCRIPTION:' line found in response")

    search_from = desc_m.end()
    qg_m = QUICKGUIDE_RE.search(content, search_from)
    body_m = BODY_DELIM_RE.search(content, search_from)

    quickguide = []
    if qg_m and (not body_m or qg_m.start() < body_m.start()):
        body_m = BODY_DELIM_RE.search(content, qg_m.end())
        if not body_m:
            raise ValueError("No 'BODY:' marker found after QUICKGUIDE")
        qg_block = content[qg_m.end():body_m.start()]
        quickguide = [
            BULLET_PREFIX_RE.sub('', line.strip()).strip()
            for line in qg_block.splitlines()
            if line.strip()
        ]

    if not body_m:
        raise ValueError("No 'BODY:' marker found after DESCRIPTION")

    title = title_m.group(1).strip()
    description = desc_m.group(1).strip()
    body = content[body_m.end():].strip()

    if not title:
        raise ValueError("TITLE is empty")
    if not description:
        raise ValueError("DESCRIPTION is empty")
    if not body:
        raise ValueError("Article body is empty")

    return title, description, quickguide, body


def _build_mdx(title: str, description: str, category: str, current_date: str,
                body: str, quickguide: list = None) -> str:
    """Assemble the final .mdx content: a code-constructed metadata block
    (never hand-written by the model) followed by the model's article body.

    If quickguide bullets were supplied, a <Callout type="info"> summary box
    is prepended to the body — Python owns the wrapper markup (component
    tag, bullet list formatting) so it can never come out malformed; the
    model only ever supplies plain bullet text via the QUICKGUIDE: section."""
    metadata = (
        "export const metadata = {\n"
        f"  title: {json.dumps(title, ensure_ascii=False)},\n"
        f"  description: {json.dumps(description, ensure_ascii=False)},\n"
        f"  category: {json.dumps(category, ensure_ascii=False)},\n"
        f"  date: {json.dumps(current_date, ensure_ascii=False)},\n"
        "}"
    )
    if quickguide:
        bullets = "\n".join(f"- {b}" for b in quickguide)
        callout = f'<Callout type="info">\n**Quick Guide**\n\n{bullets}\n</Callout>\n\n'
        body = callout + body
    return f"{metadata}\n\n{body}\n"


MAX_ARTICLE_CHARS = 50_000
REPEATED_WHITESPACE_RE = re.compile(r'\s{200,}')
STARTS_WITH_METADATA_RE = re.compile(r'\Aexport const metadata\s*=\s*\{')


def _has_repeated_chunk(content: str, min_repeats: int = 10,
                         chunk_lens=(20, 40, 80, 160)) -> bool:
    """Detect a substring that consists of the same chunk repeated
    contiguously `min_repeats`+ times (degenerate non-whitespace repetition,
    e.g. a phrase or a padded table-separator run looping instead of plain
    whitespace).

    Deliberately not a backreference regex (`(.{20,}?)\\1{9,}`) — that
    pattern has catastrophic-backtracking behavior on exactly the large,
    highly-repetitive input it's meant to catch, which would hang
    validation instead of flagging it. This checks every starting position
    (needed for correctness — a repeat run can start at any offset, not just
    ones reached by skipping ahead in chunk_len-sized strides) but uses a
    cheap single-character pre-check before the full O(chunk_len) slice
    comparison, so the common (non-repeating) case stays close to O(n) per
    tested chunk length.
    """
    n = len(content)
    for chunk_len in chunk_lens:
        run_len = chunk_len * min_repeats
        if n < run_len:
            continue
        limit = n - run_len
        i = 0
        while i <= limit:
            if content[i] == content[i + chunk_len] and content[i:i + chunk_len] == content[i + chunk_len:i + 2 * chunk_len]:
                chunk = content[i:i + chunk_len]
                repeats = 2
                j = i + 2 * chunk_len
                while content[j:j + chunk_len] == chunk:
                    repeats += 1
                    j += chunk_len
                if repeats >= min_repeats:
                    return True
            i += 1
    return False


def validate_markdown(content: str) -> tuple:
    """Validate the fully-assembled .mdx content (metadata block + body).
    Returns (is_valid, error_msg).

    The start-with-metadata and duplicate-metadata checks are now mostly a
    self-consistency guard on this module's own _build_mdx() output rather
    than a defense against the model (which never writes that block
    itself) — cheap to keep, catches a bug in this code rather than a bug
    in the model's output. The remaining checks guard against known LLM
    degenerate-output failure modes in the body content: runaway output
    size, abnormally long whitespace/repeated-chunk runs (repetition traps
    during long-table generation), and stray code-fence markers.
    """
    if not content or not content.strip():
        return False, "Empty content"
    if len(content) < 200:
        return False, f"Content too short ({len(content)} chars)"
    if len(content) > MAX_ARTICLE_CHARS:
        return False, f"Content too long ({len(content)} chars) — likely a degenerate repetition loop"
    metadata_count = content.count('export const metadata')
    if metadata_count != 1:
        return False, f"Expected exactly 1 'export const metadata' block, found {metadata_count}"
    if REPEATED_WHITESPACE_RE.search(content):
        return False, "Abnormally long whitespace run detected (likely degenerate output)"
    if _has_repeated_chunk(content):
        return False, "Abnormally repeated content chunk detected (likely degenerate output)"
    if not STARTS_WITH_METADATA_RE.match(content.lstrip()):
        return False, "Content does not start with 'export const metadata = {'"
    if '```' in content:
        return False, "Stray code-fence marker (```) found in body — article content must not contain code fences"
    return True, ""


def _process_llm_response(raw_content: str, category: str, current_date: str) -> tuple:
    """Clean, parse, and assemble a raw LLM response into a validated .mdx
    string. Returns (final_content, None) on success, or (None, error) on
    failure. Shared by the initial pass and the repair pass so both go
    through identical parse/assemble/validate logic.
    """
    cleaned = clean_llm_output(raw_content)
    try:
        title, description, quickguide, body = _parse_llm_output(cleaned)
    except ValueError as e:
        return None, str(e)
    final = _build_mdx(title, description, category, current_date, body, quickguide)
    is_valid, err = validate_markdown(final)
    if not is_valid:
        return None, err
    return final, None


# ── main logic ──────────────────────────────────────────────────

async def run_generate(
    project: str,
    keywords_file: str,
    prompt_path: str = None,
    overwrite: bool = False,
    test: bool = False,
):
    """Generate articles from collected material."""
    Config.init(project)

    print("=" * 70)
    print(f"  Step 3: Generate [{project}]")
    print("=" * 70)

    # Load prompt template
    prompt_template = load_prompt_template(prompt_path)
    print(f"  📝 Prompt template loaded ({len(prompt_template)} chars)\n")

    try:
        with open(keywords_file, 'r', encoding='utf-8') as f:
            keyword_input = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        keyword_input = {}
    trusted_context = keyword_input.get('trusted_context') or {}

    # Load keywords with categories from search_results.json
    search_results_path = f"{Config.OUT_DIR}/search_results.json"
    try:
        with open(search_results_path, 'r', encoding='utf-8') as f:
            sr_data = json.load(f)
        keyword_entries = []
        for kw in sr_data.get('keywords', []):
            keyword_entries.append({
                'keyword': kw['keyword'],
                'category': kw.get('category', ''),
                'search_evidence': {
                    'youtube_titles': [
                        {'title': item.get('title'), 'url': item.get('url')}
                        for item in (kw.get('youtube', {}).get('items') or [])
                        if item.get('selected') and item.get('title')
                    ][:8],
                    'web_results': [
                        {'title': item.get('title'), 'url': item.get('url'), 'snippet': item.get('snippet')}
                        for item in (kw.get('web', {}).get('items') or [])
                        if item.get('selected') and item.get('title')
                    ][:5],
                },
            })
    except FileNotFoundError:
        # Fallback: load from keywords file directly
        try:
            with open(keywords_file, 'r', encoding='utf-8') as f:
                kw_data = json.load(f)
        except FileNotFoundError:
            print(f"  ❌ Keywords file not found: {keywords_file}")
            return

        keyword_entries = []
        if 'categories' in kw_data:
            for cat in kw_data['categories']:
                for kw in cat.get('keywords', []):
                    keyword_entries.append({'keyword': kw.strip(), 'category': cat.get('category', '')})
        else:
            for kw in kw_data.get('keywords', []):
                keyword_entries.append({'keyword': kw.strip(), 'category': ''})

    if not keyword_entries:
        print("  ❌ No keywords found")
        return

    if test:
        keyword_entries = keyword_entries[:2]
        print(f"  🧪 TEST MODE: {len(keyword_entries)} keywords\n")

    # Load collected material for each keyword
    collected_dir = f"{Config.OUT_DIR}/collected"
    articles_dir = f"{Config.DATA_DIR}/articles/en"
    ensure_dir(articles_dir)

    prompts = []
    skipped_no_data = 0
    skipped_exists = 0
    skipped_rejected = 0
    fingerprints_path = f"{Config.OUT_DIR}/generation_fingerprints.json"
    qa_cache_path = f"{Config.OUT_DIR}/qa_results.json"
    fingerprints = load_json(fingerprints_path) if os.path.exists(fingerprints_path) else {}
    qa_cache = load_json(qa_cache_path) if os.path.exists(qa_cache_path) else {}

    for entry in keyword_entries:
        keyword = entry['keyword']
        category = entry.get('category', '')
        slug = keyword_to_slug(keyword)
        fname = keyword_to_filename(keyword)

        # Look for collected file in category subdir or flat
        if category:
            cat_slug = category.lower().replace(' ', '-')
            collected_path = f"{collected_dir}/{cat_slug}/{fname}.json"
            if not os.path.exists(collected_path):
                collected_path = f"{collected_dir}/{fname}.json"
            output_path = f"{articles_dir}/{cat_slug}/{slug}.mdx"
        else:
            collected_path = f"{collected_dir}/{fname}.json"
            output_path = f"{articles_dir}/{slug}.mdx"

        if not os.path.exists(collected_path):
            skipped_no_data += 1
            continue

        if os.path.exists(output_path) and not overwrite:
            skipped_exists += 1
            continue

        # Load collected content
        merged = load_json(collected_path)
        if not merged or merged.get('total_sources', 0) == 0:
            skipped_no_data += 1
            continue

        enriched = dict(merged)
        enriched['trusted_game_context'] = trusted_context
        enriched['search_evidence'] = entry.get('search_evidence') or {}
        enriched['target_keyword'] = keyword
        merged_json = json.dumps(enriched, indent=2, ensure_ascii=False)
        current_date = datetime.now().strftime('%Y-%m-%d')
        cat_slug_final = cat_slug if category else "general"

        prompt = prompt_template.format(
            merged_data=merged_json,
            current_date=current_date,
            category=cat_slug_final,
        )
        relative_output = str(Path(output_path).relative_to(Path(articles_dir))).replace('\\', '/')
        source_fingerprint = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
        cached_rejection = qa_cache.get(relative_output) or {}
        if (
            not overwrite
            and cached_rejection.get('verdict') == 'OFF_TOPIC'
            and cached_rejection.get('source_fingerprint') == source_fingerprint
        ):
            skipped_rejected += 1
            continue

        prompts.append((prompt, {
            'keyword': keyword,
            'slug': slug,
            'output_path': output_path,
            'prompt': prompt,
            'category': cat_slug_final,
            'current_date': current_date,
            'relative_output': relative_output,
            'source_fingerprint': source_fingerprint,
        }))

    if skipped_no_data > 0:
        print(f"  ⏭️  Skipped {skipped_no_data} keywords (no collected data)")
    if skipped_exists > 0:
        print(f"  ⏭️  Skipped {skipped_exists} keywords (article exists)")
    if skipped_rejected > 0:
        print(f"  ⏭️  Skipped {skipped_rejected} keywords (same source pack was already rejected by QA)")

    if not prompts:
        print("\n  ℹ️  Nothing to generate")
        return

    print(f"\n  📝 Generating {len(prompts)} articles...")
    print(f"     Batch size: {Config.GENERATE_BATCH_SIZE}")
    print(f"     Model: {Config.LLM_MODEL}\n")

    # Generate
    client = LLMClient()
    results = await client.generate_batch(prompts)

    # Save results with repair
    saved = 0
    failed = 0
    repair_prompts = []

    for meta, content in results:
        if not content:
            failed += 1
            continue

        final, err = _process_llm_response(content, meta['category'], meta['current_date'])

        if final:
            output_path = meta['output_path']
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final)
            fingerprints[meta['relative_output']] = meta['source_fingerprint']
            saved += 1
            print(f"  ✅ {meta['slug']}.mdx")
        else:
            # Queue for repair
            repair_prompt = _build_repair_prompt(meta, content, err)
            repair_prompts.append((repair_prompt, meta))

    # Repair pass
    if repair_prompts:
        print(f"\n  🔧 Repairing {len(repair_prompts)} articles...")
        repair_results = await client.generate_batch(
            repair_prompts,
            batch_size=min(10, len(repair_prompts)),
        )

        for meta, content in repair_results:
            if not content:
                failed += 1
                continue
            final, err = _process_llm_response(content, meta['category'], meta['current_date'])
            if final:
                output_path = meta['output_path']
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(final)
                fingerprints[meta['relative_output']] = meta['source_fingerprint']
                saved += 1
                print(f"  ✅ (repaired) {meta['slug']}.mdx")
            else:
                failed += 1
                print(f"  ❌ {meta['slug']}.mdx — still invalid after repair: {err}")

    save_json(fingerprints, fingerprints_path)

    # Summary
    print("\n" + "=" * 70)
    print(f"  {'✅' if failed == 0 else '⚠️ '} Generate complete")
    print("=" * 70)
    print(f"  Saved:   {saved}")
    print(f"  Failed:  {failed}")
    print(f"  Output:  {articles_dir}/")
    client.print_stats()
    print("=" * 70)


def _build_repair_prompt(meta: dict, content: str, error: str) -> str:
    """Build a repair prompt asking LLM to fix the invalid output.

    Reuses the original fully-substituted prompt (reference material +
    writing requirements, stored in meta['prompt']) as the base, then
    appends the repair note — mirrors translate.py's _build_repair_prompt().
    """
    keyword = meta.get('keyword', 'unknown')
    base = meta.get('prompt', '')
    return (
        base
        + f"\n\n===\n\n"
        f"The previous response for keyword \"{keyword}\" had issues:\n"
        f"  Error: {error}\n\n"
        f"Previous response (for reference, do NOT repeat the same mistakes):\n"
        f"{content[:2000]}\n\n"
        f"Regenerate a COMPLETE response from scratch, following the reference material "
        f"and writing requirements above. Fix the issue described above.\n"
        f"Output in the exact TITLE: / DESCRIPTION: / QUICKGUIDE: (optional) / BODY: format "
        f"described in the Output Format section. Do NOT output a JS/JSON metadata block yourself. "
        f"Do NOT wrap any part of the response in code blocks."
    )
