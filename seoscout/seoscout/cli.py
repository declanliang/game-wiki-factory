#!/usr/bin/env python3
"""
seoscout CLI — unified entry point.

Usage:
    seoscout classify --keywords FILE [--overwrite]
    seoscout search --keywords FILE
    seoscout collect --keywords FILE
    seoscout generate --keywords FILE [--prompt FILE] [--overwrite] [--test]
    seoscout qa --keywords FILE [--overwrite] [--prompt FILE]
    seoscout translate --keywords FILE --lang es,pt,de [--prompt FILE] [--overwrite] [--test]
    seoscout run --keywords FILE
"""

import asyncio
import argparse
import json
import os
import sys

from . import __version__


def _derive_project(keywords_file: str) -> str:
    """Derive project name from game_name in JSON, or fall back to filename."""
    try:
        with open(keywords_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        game_name = data.get('game_name', '').strip()
        if game_name:
            return game_name.replace(' ', '_').lower()
    except Exception:
        pass
    base = os.path.splitext(os.path.basename(keywords_file))[0]
    return base.replace(' ', '_').lower()


def main():
    parser = argparse.ArgumentParser(
        prog="seoscout",
        description="Keyword research, content collection, article generation & translation CLI for SEO"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── classify ──
    classify_parser = subparsers.add_parser(
        "classify",
        help="Auto-classify a flat keyword list into categories using the LLM (opt-in via 'category_options')"
    )
    classify_parser.add_argument(
        "--keywords", "-k", required=True,
        help="Path to keywords JSON file"
    )
    classify_parser.add_argument(
        "--prompt",
        help="Path to custom classify prompt template (default: built-in)"
    )
    classify_parser.add_argument(
        "--overwrite", action="store_true",
        help="Reclassify even if classified_keywords.json already exists"
    )

    # ── search ──
    search_parser = subparsers.add_parser(
        "search",
        help="Search keywords on YouTube and Google → search_results.json"
    )
    search_parser.add_argument(
        "--keywords", "-k", required=True,
        help="Path to keywords JSON file"
    )

    # ── collect ──
    collect_parser = subparsers.add_parser(
        "collect",
        help="Collect YouTube transcripts and web content from search results"
    )
    collect_parser.add_argument(
        "--project", "-p",
        help="Project name (auto-derived from keywords file if not set)"
    )
    collect_parser.add_argument(
        "--keywords", "-k",
        help="Keywords JSON file (used to derive project name if --project not set)"
    )

    # ── generate ──
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate Markdown articles from collected material using LLM"
    )
    gen_parser.add_argument(
        "--keywords", "-k", required=True,
        help="Path to keywords JSON file"
    )
    gen_parser.add_argument(
        "--prompt",
        help="Path to custom prompt template (default: built-in)"
    )
    gen_parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing articles"
    )
    gen_parser.add_argument(
        "--test", action="store_true",
        help="Test mode: only generate 2 articles"
    )

    # ── qa ──
    qa_parser = subparsers.add_parser(
        "qa",
        help="Review generated English articles for topic relevance using the LLM; deletes off-topic ones (and any existing translations of them)"
    )
    qa_parser.add_argument(
        "--keywords", "-k", required=True,
        help="Path to keywords JSON file"
    )
    qa_parser.add_argument(
        "--prompt",
        help="Path to custom QA prompt template (default: built-in)"
    )
    qa_parser.add_argument(
        "--overwrite", action="store_true",
        help="Re-review even if qa_results.json already has a verdict for an article"
    )

    # ── translate ──
    trans_parser = subparsers.add_parser(
        "translate",
        help="Translate English articles to other languages using LLM"
    )
    trans_parser.add_argument(
        "--keywords", "-k", required=True,
        help="Path to keywords JSON file (used to derive project name)"
    )
    trans_parser.add_argument(
        "--lang", "-l",
        help="Target languages, comma-separated (e.g. es,pt,de,fr,ja). If not set, reads from 'languages' field in keywords JSON."
    )
    trans_parser.add_argument(
        "--prompt",
        help="Path to custom translation prompt template (default: built-in)"
    )
    trans_parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing translations"
    )
    trans_parser.add_argument(
        "--test", action="store_true",
        help="Test mode: only translate 1 article"
    )

    # ── run (search + collect + generate) ──
    run_parser = subparsers.add_parser(
        "run",
        help="Search, collect, generate (and translate if languages set) in one step"
    )
    run_parser.add_argument(
        "--keywords", "-k", required=True,
        help="Path to keywords JSON file"
    )
    run_parser.add_argument(
        "--prompt",
        help="Path to custom prompt template for generation"
    )
    run_parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing articles"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Derive project name
    if args.command in ("search", "generate", "run", "classify", "qa"):
        args.project = _derive_project(args.keywords)
        print(f"📁 Project: {args.project}\n")
    elif args.command == "collect":
        if args.project:
            pass
        elif args.keywords:
            args.project = _derive_project(args.keywords)
        else:
            print("❌ Need --project or --keywords to identify project")
            sys.exit(1)
    elif args.command == "translate":
        args.project = _derive_project(args.keywords)
        print(f"📁 Project: {args.project}\n")

    if args.command == "classify":
        asyncio.run(_run_classify(args))
    elif args.command == "search":
        asyncio.run(_run_search(args))
    elif args.command == "collect":
        asyncio.run(_run_collect(args))
    elif args.command == "generate":
        asyncio.run(_run_generate(args))
    elif args.command == "qa":
        asyncio.run(_run_qa(args))
    elif args.command == "translate":
        asyncio.run(_run_translate(args))
    elif args.command == "run":
        asyncio.run(_run_all(args))


async def _run_classify(args):
    from .classify import run_classify
    await run_classify(args.project, args.keywords, prompt_path=args.prompt, overwrite=args.overwrite)


async def _run_search(args):
    from .search import run_search
    await run_search(args.project, args.keywords)


async def _run_collect(args):
    from .collect import run_collect
    await run_collect(args.project)


async def _run_generate(args):
    from .generate import run_generate
    await run_generate(
        args.project,
        args.keywords,
        prompt_path=args.prompt,
        overwrite=args.overwrite,
        test=args.test,
    )


async def _run_qa(args):
    from .qa import run_qa
    await run_qa(args.project, args.keywords, prompt_path=args.prompt, overwrite=args.overwrite)


async def _run_translate(args):
    from .translate import run_translate
    from .core.utils import load_languages_from_json

    # --lang not provided → read from keywords JSON
    if not args.lang:
        langs = load_languages_from_json(args.keywords)
        if not langs:
            print("❌ No --lang specified and no 'languages' field in keywords JSON")
            sys.exit(1)
        args.lang = ",".join(langs)
        print(f"🌐 Languages from JSON: {args.lang}\n")

    await run_translate(
        args.project,
        args.lang,
        prompt_path=args.prompt,
        overwrite=args.overwrite,
        test=args.test,
    )


async def _run_all(args):
    from .classify import run_classify, should_auto_classify
    from .search import run_search
    from .collect import run_collect
    from .generate import run_generate
    from .qa import run_qa
    from .translate import run_translate
    from .core.utils import load_languages_from_json

    if should_auto_classify(args.keywords):
        await run_classify(args.project, args.keywords, overwrite=args.overwrite)

    await run_search(args.project, args.keywords)
    await run_collect(args.project)
    await run_generate(
        args.project,
        args.keywords,
        prompt_path=args.prompt,
        overwrite=args.overwrite,
    )

    # Mandatory — not skippable. Unreviewed output routinely ships off-topic
    # articles that pass every structural check (see doc/文不对题问题记录.md);
    # QA is what makes the rest of the pipeline's output actually usable.
    await run_qa(args.project, args.keywords, overwrite=args.overwrite)

    # If languages are specified in JSON, auto-translate
    langs = load_languages_from_json(args.keywords)
    if langs:
        lang_str = ",".join(langs)
        print(f"\n{'='*70}")
        print(f"  Step 5: Translate [{args.project}] → {lang_str}")
        print(f"{'='*70}")
        await run_translate(
            args.project,
            lang_str,
            prompt_path=None,
            overwrite=args.overwrite,
        )


if __name__ == "__main__":
    main()
