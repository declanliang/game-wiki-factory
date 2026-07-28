#!/usr/bin/env python3
"""
Step 5: Translate articles to multiple languages.

Reads articles/en/*.mdx (or *.md), translates via LLM, outputs to articles/{lang}/*.mdx.
"""

import asyncio
import json
import os
import re
from pathlib import Path
from string import Template
from datetime import datetime

from .core.config import Config
from .core.llm_client import LLMClient
from .core.utils import ensure_dir, extract_source_fields
from .markdown_normalize import normalize_raw_html_blocks


class TranslationError(RuntimeError):
    """Raised when one or more required translations could not be saved."""


# ── language map ────────────────────────────────────────────────

LANG_NAMES = {
    'es': 'Spanish',
    'pt': 'Portuguese (Brazil)',
    'de': 'German',
    'fr': 'French',
    'ja': 'Japanese',
    'ar': 'Arabic',
    'ko': 'Korean',
    'ru': 'Russian',
    'zh': 'Chinese',
    'vi': 'Vietnamese',
    'th': 'Thai',
    'id': 'Indonesian',
    'tr': 'Turkish',
    'it': 'Italian',
    'pl': 'Polish',
    'nl': 'Dutch',
    'hi': 'Hindi',
}


# ── helpers ─────────────────────────────────────────────────────

def load_prompt_template(prompt_path: str = None) -> str:
    """Load translation prompt template from file or built-in default.

    Template variables (string.Template $var syntax): $language_name (target
    language display name, e.g. "Spanish"), $lang_code (e.g. "es"), $title,
    $description, $body (the English article's title/description/body,
    extracted from its metadata block by core.utils.extract_source_fields() — the
    template never sees or reproduces the `export const metadata = {...}`
    JS syntax itself; that's assembled by code, same as generate.py).

    Deliberately not documented as a leading comment inside the .md file
    itself — see generate.py's load_prompt_template() for why (that comment
    text becomes the literal first thing the model reads, and has been
    observed leaking into real output).
    """
    if prompt_path:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    default = Path(__file__).parent / "templates" / "translate.md"
    with open(default, 'r', encoding='utf-8') as f:
        return f.read()


def clean_llm_output(content: str) -> str:
    """Strip outer code fences (handles any language tag like ```javascript, ```mdx, etc.)."""
    content = content.strip()
    # Match opening code fence with optional language tag (e.g. ```javascript, ```mdx, ```markdown)
    if content.startswith('```'):
        first_newline = content.find('\n')
        if first_newline != -1:
            content = content[first_newline + 1:]
        else:
            content = content[3:]
    if content.rstrip().endswith('```'):
        content = content.rstrip()[:-3].rstrip()
    return normalize_raw_html_blocks(content)


# ── source parsing / output assembly ────────────────────────────
#
# Same architecture as generate.py: the model never hand-writes the
# `export const metadata = {...}` JS block, either as input context to
# translate from field-by-field, or as output to produce. We extract
# title/description/category/date/body out of the English source
# deterministically (via core.utils.extract_source_fields(), shared with
# qa.py), ask the model to translate just title/description/body, and
# reassemble the final metadata block ourselves (category/date are copied
# through unchanged — they were never meant to be translated).

TITLE_RE = re.compile(r'^TITLE:\s*(.+)$', re.MULTILINE)
DESCRIPTION_RE = re.compile(r'^DESCRIPTION:\s*(.+)$', re.MULTILINE)
BODY_DELIM_RE = re.compile(r'^BODY:[ \t]*\n', re.MULTILINE)


def _parse_llm_output(content: str) -> tuple:
    """Parse the model's TITLE:/DESCRIPTION:/BODY: contract (same shape
    as generate.py's parser). Returns (title, description, body). Raises
    ValueError with a human-readable reason on failure."""
    title_m = TITLE_RE.search(content)
    if not title_m:
        raise ValueError("No 'TITLE:' line found in response")

    desc_m = DESCRIPTION_RE.search(content, title_m.end())
    if not desc_m:
        raise ValueError("No 'DESCRIPTION:' line found in response")

    delim_m = BODY_DELIM_RE.search(content, desc_m.end())
    if not delim_m:
        raise ValueError("No 'BODY:' marker found after DESCRIPTION")

    title = title_m.group(1).strip()
    description = desc_m.group(1).strip()
    body = content[delim_m.end():].strip()

    if not title:
        raise ValueError("TITLE is empty")
    if not description:
        raise ValueError("DESCRIPTION is empty")
    if not body:
        raise ValueError("Article body is empty")

    return title, description, body


def _build_mdx(title: str, description: str, category: str, date: str, body: str) -> str:
    """Assemble the final .mdx content — see generate.py's version (same
    rationale: category/date are copied through unchanged, never trusted
    from the model, and title/description are JSON-escaped for safety)."""
    metadata = (
        "export const metadata = {\n"
        f"  title: {json.dumps(title, ensure_ascii=False)},\n"
        f"  description: {json.dumps(description, ensure_ascii=False)},\n"
        f"  category: {json.dumps(category, ensure_ascii=False)},\n"
        f"  date: {json.dumps(date, ensure_ascii=False)},\n"
        "}"
    )
    return f"{metadata}\n\n{body}\n"


def _common_slug_prefix(stems: list[str]) -> list[str]:
    token_lists = [stem.split('-') for stem in stems]
    if not token_lists:
        return []
    prefix = []
    for values in zip(*token_lists):
        if len(set(values)) != 1:
            break
        prefix.append(values[0])
    return prefix


def _unique_title(title: str, stem: str, common_prefix: list[str], lang_code: str) -> str:
    tokens = stem.split('-')[len(common_prefix):] or stem.split('-')[-4:]
    qualifier = ' '.join(token.capitalize() for token in tokens[-6:] if token)
    limit = 36 if lang_code in CJK_LANGUAGES else 60
    # Preserve enough of the localized title to remain readable while keeping
    # the source topic phrase visible. English game/entity terms are common in
    # localized game searches and are safer than inventing a new translation.
    qualifier_limit = min(26, max(12, limit // 2))
    qualifier = _compact_serp_field(qualifier, qualifier_limit, 'en')
    suffix = f" · {qualifier}"
    base_limit = max(8, limit - len(suffix))
    base = _compact_serp_field(title, base_limit, lang_code)
    return f"{base}{suffix}"[:limit].rstrip(" ·-–—")


def deduplicate_translated_titles(articles_root: Path, target_langs: list[str]) -> int:
    """Deterministically disambiguate model-collapsed article titles.

    Different focused pages sometimes receive the same generic title even when
    their bodies and source keywords are distinct. This can happen in English
    generation as well as translation. Keep the checkpoint and append the
    unique source-topic slug instead of regenerating a complete article.
    """
    changed = 0
    for lang_code in target_langs:
        locale_root = articles_root / lang_code
        if not locale_root.is_dir():
            continue
        records = []
        for path in sorted(locale_root.glob('**/*.mdx')):
            try:
                fields = extract_source_fields(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            records.append((path, fields))
        groups: dict[str, list[tuple[Path, dict]]] = {}
        for record in records:
            groups.setdefault(record[1]['title'].casefold(), []).append(record)
        for group in groups.values():
            if len(group) < 2:
                continue
            common_prefix = _common_slug_prefix([path.stem for path, _fields in group])
            for path, fields in group:
                unique = _unique_title(fields['title'], path.stem, common_prefix, lang_code)
                content = _build_mdx(
                    unique,
                    fields['description'],
                    fields['category'],
                    fields['date'],
                    fields['body'],
                )
                path.write_text(content, encoding='utf-8')
                changed += 1
                print(f"  [TITLE] [{lang_code.upper()}] disambiguated title: {path.name}")
    return changed


def _unique_description(description: str, stem: str, common_prefix: list[str], lang_code: str) -> str:
    """Add a compact, deterministic topic qualifier to a collapsed SERP description."""
    tokens = stem.split('-')[len(common_prefix):] or stem.split('-')[-4:]
    qualifier = ' '.join(token.capitalize() for token in tokens[-6:] if token)
    limit = 90 if lang_code in CJK_LANGUAGES else 160
    suffix = f" — {qualifier}."
    base = _compact_serp_field(
        description.rstrip(" .!?。！？…"), max(24, limit - len(suffix)), lang_code,
        prefer_sentence=True,
    ).rstrip(" .!?。！？…")
    return f"{base}{suffix}"[:limit].rstrip(" ·-–—") + "."


def deduplicate_translated_descriptions(articles_root: Path, target_langs: list[str]) -> int:
    """Prevent localized articles with different intent from sharing one SERP description.

    Translation models occasionally collapse two narrowly related pages into the
    same description.  This is deterministic metadata-only repair: preserve the
    body, retain the original description, and append the source-topic slug.
    """
    changed = 0
    for lang_code in target_langs:
        locale_root = articles_root / lang_code
        if not locale_root.is_dir():
            continue
        records = []
        for path in sorted(locale_root.glob('**/*.mdx')):
            try:
                fields = extract_source_fields(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            records.append((path, fields))
        groups: dict[str, list[tuple[Path, dict]]] = {}
        for record in records:
            groups.setdefault(record[1]['description'].casefold(), []).append(record)
        for group in groups.values():
            if len(group) < 2:
                continue
            common_prefix = _common_slug_prefix([path.stem for path, _fields in group])
            for path, fields in group:
                unique = _unique_description(
                    fields['description'], path.stem, common_prefix, lang_code,
                )
                content = _build_mdx(
                    fields['title'], unique, fields['category'], fields['date'], fields['body'],
                )
                path.write_text(content, encoding='utf-8')
                changed += 1
                print(f"  [DESCRIPTION] [{lang_code.upper()}] disambiguated description: {path.name}")
    return changed


MAX_ARTICLE_CHARS = 50_000
REPEATED_WHITESPACE_RE = re.compile(r'\s{200,}')
STARTS_WITH_METADATA_RE = re.compile(r'\Aexport const metadata\s*=\s*\{')
HEADING_RE = re.compile(r'^(#{2,6})[ \t]+\S', re.MULTILINE)
CALLOUT_RE = re.compile(r'<Callout\b[^>]*>|</Callout>')
TERMINAL_PUNCTUATION_RE = re.compile(r'[.!?。！？…|>\])}\"\'’”]$')
CJK_LANGUAGES = {'ja', 'ko', 'zh'}
STRUCTURAL_LINE_PATTERNS = {
    'list items': re.compile(r'^\s*[-*+]\s+\S', re.MULTILINE),
    'numbered items': re.compile(r'^\s*\d+[.)]\s+\S', re.MULTILINE),
    'table rows': re.compile(r'^\s*\|.*\|\s*$', re.MULTILINE),
}
FORMATTED_QUESTION_RE = re.compile(
    r'^\s*\*\*[^\n]*(?:\?|？)\*\*\s*$', re.MULTILINE
)
BOLD_STANDALONE_RE = re.compile(r'^\s*\*\*[^\n]+\*\*\s*$', re.MULTILINE)
DANGLING_SERP_SUFFIX_RE = re.compile(
    r"\s+(?:and|or|with|for|to|the|a|an|in|on|at|of|from|into|this|that|your|our|"
    r"und|oder|mit|für|y|o|con|para|et|ou|avec|pour)[.!?。！？…]*$",
    re.IGNORECASE,
)


def _trim_dangling_serp_suffix(value: str) -> str:
    """Remove a connector left behind by a model-truncated SERP field."""
    trimmed = value.strip()
    while DANGLING_SERP_SUFFIX_RE.search(trimmed):
        trimmed = DANGLING_SERP_SUFFIX_RE.sub("", trimmed).rstrip(" ,.;:!?。！？…-–—&")
    return trimmed


def _compact_serp_field(
    value: str, limit: int, lang_code: str, *, prefer_sentence: bool = False
) -> str:
    """Shorten over-limit translated metadata without retranslating the body."""
    value = value.strip()
    if lang_code not in CJK_LANGUAGES:
        value = _trim_dangling_serp_suffix(value)
    if len(value) <= limit:
        return value
    if prefer_sentence:
        prefix = value[:limit]
        sentence_ends = [match.end() for match in re.finditer(r"[.!?。！？]", prefix)]
        # A concise complete sentence is preferable to appending a fragment
        # merely to consume more of the SERP description allowance.
        usable = [end for end in sentence_ends if end >= max(30, int(limit * 0.35))]
        if usable:
            return prefix[:usable[-1]].strip()
    if lang_code in CJK_LANGUAGES:
        candidate = value[: max(1, limit - 1)].rstrip(" ,.;:!?、。，：；！？-–—")
        return candidate + ("…" if prefer_sentence else "")
    candidate = value[:limit + 1].rsplit(" ", 1)[0]
    if len(candidate) < max(20, int(limit * 0.6)):
        candidate = value[:limit]
    candidate = candidate.rstrip(" ,.;:!?-–—&")
    if not prefer_sentence:
        candidate = _trim_dangling_serp_suffix(candidate)
        return candidate
    return candidate[: max(1, limit - 1)].rstrip(" ,.;:!?-–—&") + "…"


def _compact_overlong_metadata(raw_content: str, lang_code: str) -> str | None:
    """Reuse a complete translation body while compacting only SERP fields.

    Retrying an entire article because a title is a few characters too long is
    expensive and can introduce a new structural failure. The normal parser
    and source-completeness validation still run after this transformation.
    """
    cleaned = clean_llm_output(raw_content)
    try:
        title, description, body = _parse_llm_output(cleaned)
    except ValueError:
        return None
    is_cjk = lang_code in CJK_LANGUAGES
    title_limit = 36 if is_cjk else 60
    description_limit = 90 if is_cjk else 160
    compact_title = _compact_serp_field(title, title_limit, lang_code)
    compact_description = _compact_serp_field(
        description, description_limit, lang_code, prefer_sentence=True
    )
    if compact_title == title and compact_description == description:
        return None
    return (
        f"TITLE: {compact_title}\n"
        f"DESCRIPTION: {compact_description}\n"
        f"BODY:\n{body}"
    )


def normalize_existing_metadata(articles_root: Path, target_langs: list[str]) -> int:
    """Repair mechanically incomplete localized SERP fields in valid checkpoints.

    This runs before a no-overwrite resume, so an old checkpoint that ended in
    a dangling connector can proceed without regenerating its article body.
    """
    changed = 0
    for lang_code in target_langs:
        locale_root = articles_root / lang_code
        if not locale_root.is_dir():
            continue
        limit = 36 if lang_code in CJK_LANGUAGES else 60
        description_limit = 90 if lang_code in CJK_LANGUAGES else 160
        for path in sorted(locale_root.glob("**/*.mdx")):
            try:
                fields = extract_source_fields(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            title = _compact_serp_field(fields["title"], limit, lang_code)
            description = _compact_serp_field(
                fields["description"], description_limit, lang_code, prefer_sentence=True,
            )
            if title == fields["title"] and description == fields["description"]:
                continue
            path.write_text(
                _build_mdx(title, description, fields["category"], fields["date"], fields["body"]),
                encoding="utf-8",
            )
            changed += 1
            print(f"  [METADATA] [{lang_code.upper()}] normalized: {path.name}")
    return changed


def _has_repeated_chunk(content: str, min_repeats: int = 10,
                         chunk_lens=(20, 40, 80, 160)) -> bool:
    """Detect a substring that consists of the same chunk repeated
    contiguously `min_repeats`+ times — see generate.py's version for the
    full rationale (a backreference regex here has catastrophic-backtracking
    behavior on exactly the large, highly-repetitive input it targets, and a
    naive chunk_len-stride scan can miss a run that starts at an unaligned
    offset — this checks every position with a cheap pre-check to stay fast).
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
    See generate.py's validate_markdown() for the full rationale — same
    checks, same reasoning, kept in sync between the two modules.
    """
    if not content or not content.strip():
        return False, "Empty content"
    if len(content) < 100:
        return False, f"Too short ({len(content)} chars)"
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


def validate_translation_against_source(
    content: str,
    source_body: str,
    lang_code: str,
) -> tuple:
    """Reject incomplete translation output before it becomes a checkpoint.

    Provider-side reasoning tokens share the completion budget with visible
    output for some models.  A response can therefore be syntactically
    parseable while ending halfway through the article.  Translation is a
    structure-preserving task, so headings and Callout tags give us a cheap,
    deterministic completeness contract without another LLM call.
    """
    is_valid, err = validate_markdown(content)
    if not is_valid:
        return False, err

    try:
        translated_body = extract_source_fields(content)['body']
    except ValueError as exc:
        return False, str(exc)

    source_headings = HEADING_RE.findall(source_body)
    translated_headings = HEADING_RE.findall(translated_body)
    if translated_headings != source_headings:
        return False, (
            "Heading structure differs from source "
            f"({len(translated_headings)}/{len(source_headings)} headings)"
        )

    def callout_signature(body: str) -> list[str]:
        return [
            'close' if token.startswith('</') else 'open'
            for token in CALLOUT_RE.findall(body)
        ]

    source_callouts = callout_signature(source_body)
    translated_callouts = callout_signature(translated_body)
    if translated_callouts != source_callouts:
        return False, (
            "Callout structure differs from source "
            f"({translated_callouts!r} != {source_callouts!r})"
        )

    # Heading levels and Callout order must match exactly.  For other
    # Markdown structures, translations may add localized emphasis but must
    # never drop structures that exist in the source (for example the final
    # FAQ questions after a token-limit truncation).
    for label, pattern in STRUCTURAL_LINE_PATTERNS.items():
        source_count = len(pattern.findall(source_body))
        translated_count = len(pattern.findall(translated_body))
        if translated_count < source_count:
            return False, (
                f"Translation dropped {label} "
                f"({translated_count}/{source_count})"
            )

    # A Japanese FAQ prompt may legitimately end in a full stop or omit the
    # question mark while preserving the source's standalone bold structure.
    # Count all standalone bold lines on both sides so punctuation differences
    # do not trigger endless retranslations, but a genuinely dropped prompt
    # still fails deterministically.
    source_question_count = len(FORMATTED_QUESTION_RE.findall(source_body))
    if source_question_count:
        source_bold_count = len(BOLD_STANDALONE_RE.findall(source_body))
        translated_bold_count = len(BOLD_STANDALONE_RE.findall(translated_body))
        if translated_bold_count < source_bold_count:
            non_question_bold_count = source_bold_count - source_question_count
            translated_question_count = max(
                0, translated_bold_count - non_question_bold_count
            )
            return False, (
                "Translation dropped formatted questions "
                f"({translated_question_count}/{source_question_count})"
            )

    # CJK translations use substantially fewer characters than English;
    # Latin-script translations normally stay close to the source length.
    # CJK prose routinely conveys the same fully structured guide in materially
    # fewer characters than English.  Heading/callout/list/FAQ parity and a
    # terminal sentence still guard against truncation; 0.40 avoids rejecting
    # complete Japanese checkpoints merely for being concise.
    minimum_ratio = 0.40 if lang_code in CJK_LANGUAGES else 0.80
    length_ratio = len(translated_body) / max(1, len(source_body))
    if length_ratio < minimum_ratio:
        return False, (
            f"Translation is likely truncated (body length ratio "
            f"{length_ratio:.2f} < {minimum_ratio:.2f})"
        )

    last_line = next(
        (line.strip() for line in reversed(translated_body.splitlines()) if line.strip()),
        '',
    )
    if last_line and not TERMINAL_PUNCTUATION_RE.search(last_line):
        return False, "Translation ends without terminal punctuation (likely truncated)"

    return True, ""


def _process_llm_response(
    raw_content: str,
    category: str,
    date: str,
    source_body: str = None,
    lang_code: str = '',
) -> tuple:
    """Clean, parse, and assemble a raw LLM response into a validated .mdx
    string. Returns (final_content, None) on success, or (None, error) on
    failure. Shared by the initial pass and the repair pass."""
    cleaned = clean_llm_output(raw_content)
    try:
        title, description, body = _parse_llm_output(cleaned)
    except ValueError as e:
        return None, str(e)
    is_cjk = lang_code in CJK_LANGUAGES
    title_limit = 36 if is_cjk else 60
    description_limit = 90 if is_cjk else 160
    if len(title) > title_limit:
        return None, f"Translated TITLE is too long ({len(title)} chars; maximum {title_limit} for {lang_code})"
    if len(description) > description_limit:
        return None, f"Translated DESCRIPTION is too long ({len(description)} chars; maximum {description_limit} for {lang_code})"
    final = _build_mdx(title, description, category, date, body)
    is_valid, err = validate_markdown(final)
    if not is_valid:
        return None, err
    if source_body is not None:
        is_complete, err = validate_translation_against_source(
            final,
            source_body,
            lang_code,
        )
        if not is_complete:
            return None, err
    return final, None


# ── main logic ──────────────────────────────────────────────────

async def run_translate(
    project: str,
    lang: str,
    prompt_path: str = None,
    overwrite: bool = False,
    test: bool = False,
):
    """
    Translate English articles to target languages.

    Args:
        project: Project name
        lang: Comma-separated language codes (e.g. 'es,pt,de')
        prompt_path: Optional custom prompt template
        overwrite: Overwrite existing translations
        test: Only translate 1 article
    """
    Config.init(project)

    print("=" * 70)
    print(f"  Step 5: Translate [{project}]")
    print("=" * 70)

    # Parse languages (any code accepted, name resolved from map or title-cased)
    target_langs = [l.strip() for l in lang.split(',') if l.strip()]
    if not target_langs:
        print("  ❌ No target languages specified")
        return

    resolved_names = {l: LANG_NAMES.get(l, l.upper()) for l in target_langs}
    print(f"  🌍 Target: {', '.join(f'{resolved_names[l]} ({l})' for l in target_langs)}\n")

    # Load prompt template
    prompt_template_str = load_prompt_template(prompt_path)
    prompt_template = Template(prompt_template_str)

    # Find English articles (flat + category subdirs)
    en_dir = Path(Config.DATA_DIR) / "articles" / "en"
    if not en_dir.exists():
        print(f"  ❌ No English articles found at {en_dir}")
        print("     Run `seoscout generate` first")
        return

    # Read .mdx (preferred) and .md files from English articles
    mdx_files = sorted(en_dir.glob("**/*.mdx"))
    md_files = sorted(en_dir.glob("**/*.md"))
    # Deduplicate by stem: prefer .mdx over .md
    seen = set()
    articles = []
    for f in mdx_files + md_files:
        key = str(f.relative_to(en_dir).with_suffix(''))
        if key not in seen:
            seen.add(key)
            articles.append(f)

    if not articles:
        print("  ❌ No .mdx/.md files in articles/en/")
        return

    if test:
        articles = articles[:1]
        print(f"  🧪 TEST MODE: {len(articles)} article(s)\n")

    print(f"  📄 Found {len(articles)} English articles")

    # Build tasks
    all_tasks = []
    skipped_unparseable = 0
    for article_path in articles:
        try:
            en_content = article_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"  ⚠️  Can't read {article_path.name}: {e}")
            continue

        try:
            source = extract_source_fields(en_content)
        except ValueError as e:
            print(f"  ⚠️  Skipping {article_path.name}: {e}")
            skipped_unparseable += 1
            continue

        article_name = article_path.stem
        # Preserve category subdirectory structure
        relative = article_path.relative_to(en_dir)

        for lang_code in target_langs:
            # Output as .mdx (change extension if source is .md)
            out_relative = relative.with_suffix('.mdx')
            output_path = Path(Config.DATA_DIR) / "articles" / lang_code / out_relative

            if output_path.exists() and not overwrite:
                existing = output_path.read_text(encoding='utf-8')
                is_valid, cache_error = validate_translation_against_source(
                    existing,
                    source['body'],
                    lang_code,
                )
                if is_valid:
                    continue
                print(
                    f"  🔄 [{lang_code.upper()}] {article_name}.mdx "
                    f"has an invalid checkpoint: {cache_error}"
                )
                output_path.unlink()

            prompt = prompt_template.substitute(
                language_name=resolved_names[lang_code],
                lang_code=lang_code,
                title=source['title'],
                description=source['description'],
                body=source['body'],
            )

            all_tasks.append({
                'prompt': prompt,
                'lang': lang_code,
                'article_name': article_name,
                'output_path': output_path,
                'category': source['category'],
                'date': source['date'],
                'source_body': source['body'],
            })

    if skipped_unparseable > 0:
        print(f"  ⏭️  Skipped {skipped_unparseable} source article(s) that didn't match the expected metadata format")

    skipped = len(articles) * len(target_langs) - len(all_tasks) - skipped_unparseable * len(target_langs)
    if skipped > 0:
        print(f"  ⏭️  Skipped {skipped} (already translated)\n")

    articles_root = Path(Config.DATA_DIR) / "articles"
    metadata_normalized = normalize_existing_metadata(articles_root, ["en", *target_langs])
    if not all_tasks:
        deduplicate_translated_titles(articles_root, ["en", *target_langs])
        deduplicate_translated_descriptions(articles_root, ["en", *target_langs])
        if metadata_normalized:
            print(f"  Metadata normalized locally: {metadata_normalized}")
        print("  ℹ️  All articles already translated")
        return

    print(f"  📝 {len(all_tasks)} translation tasks\n")
    print(f"     Batch size: {Config.TRANSLATE_BATCH_SIZE}")
    print(f"     Batch delay: {Config.TRANSLATE_BATCH_DELAY}s")
    print(f"     Model: {Config.LLM_MODEL}\n")

    # Execute in batches
    client = LLMClient()
    client.stats['start_time'] = __import__('time').time()

    batch_size = Config.TRANSLATE_BATCH_SIZE
    batch_delay = Config.TRANSLATE_BATCH_DELAY
    saved = 0
    failed = 0

    async with __import__('aiohttp').ClientSession() as session:
        for i in range(0, len(all_tasks), batch_size):
            batch = all_tasks[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(all_tasks) + batch_size - 1) // batch_size

            print(f"  📦 Batch {batch_num}/{total_batches} ({len(batch)} tasks)...")

            tasks = [
                client.generate_single(session, t['prompt'], {
                    'keyword': t['article_name'],
                    'language': t['lang'],
                }, reasoning_effort=Config.TRANSLATE_REASONING_EFFORT)
                for t in batch
            ]
            results = await asyncio.gather(*tasks)

            for task_info, content in zip(batch, results):
                lang_code = task_info['lang']
                article_name = task_info['article_name']
                output_path = task_info['output_path']

                if not content:
                    failed += 1
                    print(f"    ❌ [{lang_code.upper()}] {article_name} — no response")
                    continue

                final, err = _process_llm_response(
                    content,
                    task_info['category'],
                    task_info['date'],
                    task_info['source_body'],
                    lang_code,
                )

                if final:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(final, encoding='utf-8')
                    saved += 1
                    print(f"    ✅ [{lang_code.upper()}] {article_name}.mdx")
                else:
                    compacted = _compact_overlong_metadata(content, lang_code)
                    compact_final, compact_error = (None, None)
                    if compacted:
                        compact_final, compact_error = _process_llm_response(
                            compacted,
                            task_info['category'],
                            task_info['date'],
                            task_info['source_body'],
                            lang_code,
                        )
                    if compact_final:
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        output_path.write_text(compact_final, encoding='utf-8')
                        saved += 1
                        print(
                            f"    ✅ [{lang_code.upper()}] {article_name}.mdx "
                            "(metadata compacted locally)"
                        )
                        continue

                    # Single repair attempt
                    repair_prompt = _build_repair_prompt(task_info, content, err)
                    repaired = await client.generate_single(
                        session, repair_prompt,
                        {'keyword': article_name, 'language': lang_code},
                        reasoning_effort=Config.TRANSLATE_REASONING_EFFORT,
                    )
                    final2, err2 = (None, None)
                    if repaired:
                        final2, err2 = _process_llm_response(
                            repaired,
                            task_info['category'],
                            task_info['date'],
                            task_info['source_body'],
                            lang_code,
                        )
                        if not final2:
                            compacted_repair = _compact_overlong_metadata(
                                repaired, lang_code
                            )
                            if compacted_repair:
                                final2, err2 = _process_llm_response(
                                    compacted_repair,
                                    task_info['category'],
                                    task_info['date'],
                                    task_info['source_body'],
                                    lang_code,
                                )
                    if final2:
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        output_path.write_text(final2, encoding='utf-8')
                        saved += 1
                        print(f"    ✅ [{lang_code.upper()}] {article_name}.mdx (repaired)")
                    else:
                        failed += 1
                        print(
                            f"    ❌ [{lang_code.upper()}] {article_name} — "
                            f"{err2 or compact_error or err}"
                        )

            if i + batch_size < len(all_tasks):
                await asyncio.sleep(batch_delay)

    metadata_normalized += normalize_existing_metadata(articles_root, ["en", *target_langs])
    deduplicated = deduplicate_translated_titles(articles_root, ["en", *target_langs])
    descriptions_deduplicated = deduplicate_translated_descriptions(
        articles_root, ["en", *target_langs]
    )

    # Summary
    print("\n" + "=" * 70)
    print(f"  {'✅' if failed == 0 else '⚠️ '} Translate complete")
    print("=" * 70)
    print(f"  Saved:   {saved}")
    print(f"  Failed:  {failed}")
    print(f"  Titles disambiguated locally: {deduplicated}")
    print(f"  Descriptions disambiguated locally: {descriptions_deduplicated}")
    print(f"  Metadata normalized locally: {metadata_normalized}")
    for lang_code in target_langs:
        lang_dir = Path(Config.DATA_DIR) / "articles" / lang_code
        count = len(list(lang_dir.glob("**/*.mdx"))) if lang_dir.exists() else 0
        print(f"  {resolved_names[lang_code]} ({lang_code}): {count} files")
    client.stats['end_time'] = __import__('time').time()
    client.print_stats()
    print("=" * 70)

    if failed:
        raise TranslationError(
            f"Translation failed for {failed} item(s); existing valid locale "
            "checkpoints were preserved. Re-run without --overwrite to retry "
            "only the missing translations."
        )


def _build_repair_prompt(task_info: dict, content: str, error: str) -> str:
    """Build a repair prompt for failed translations.

    Reuses the original fully-substituted prompt (stored in
    task_info['prompt']) as the base, then appends the repair note — mirrors
    generate.py's _build_repair_prompt().
    """
    lang_name = LANG_NAMES.get(task_info['lang'], task_info['lang'])
    article_name = task_info['article_name']
    base = task_info.get('prompt', '')
    source_body = task_info.get('source_body', '')
    structural_counts = {
        label: len(pattern.findall(source_body))
        for label, pattern in STRUCTURAL_LINE_PATTERNS.items()
    }
    structural_counts['standalone bold lines'] = len(
        BOLD_STANDALONE_RE.findall(source_body)
    )
    structural_counts['headings'] = len(HEADING_RE.findall(source_body))
    structural_counts['callout tags'] = len(CALLOUT_RE.findall(source_body))
    checklist = ', '.join(
        f"{label}: {count}" for label, count in structural_counts.items()
    )
    return (
        base
        + f"\n\n===\n\n"
        f"The previous response for \"{article_name}\" to {lang_name} had issues:\n"
        f"  Error: {error}\n\n"
        f"Regenerate the FULL response from scratch. Fix the issue above.\n"
        f"The BODY must preserve at least these source structures: {checklist}.\n"
        f"Translate the text inside every heading and standalone bold line, but "
        f"do not remove or merge any of them.\n"
        f"Output in the exact TITLE: / DESCRIPTION: / BODY: format described in the "
        f"Output Format section. Do NOT output a JS/JSON metadata block yourself. "
        f"Do NOT wrap any part of the response in code blocks. Do NOT use YAML frontmatter."
    )
