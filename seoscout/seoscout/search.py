#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 1: Search & collect metadata

Search YouTube and Web in parallel for each keyword,
output search_results.json for review.
"""

import asyncio
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Windows UTF-8 compatibility
# line_buffering=True is required — without it, TextIOWrapper defaults to
# block buffering, which silently withholds all console output (looks like
# the process is frozen) until the internal buffer fills or the process exits.
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

from .core.config import Config
from .core.youtube import YouTube
from .core.web import Web
from .core.utils import load_keywords_from_json, save_json, ensure_dir, load_json


def load_existing_results() -> Dict[str, Dict]:
    results_file = Path(Config.OUT_DIR) / "search_results.json"

    if not results_file.exists():
        return {}

    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        existing = {}
        for kw_data in data.get('keywords', []):
            keyword = kw_data['keyword']
            existing[keyword] = {
                'category': kw_data.get('category', ''),
                'youtube': kw_data.get('youtube', {'count': 0, 'items': []}),
                'web': kw_data.get('web', {'count': 0, 'items': []})
            }

        return existing
    except Exception as e:
        print(f"⚠️  Failed to load existing results: {e}")
        return {}


def filter_keywords_for_retry(
    all_keywords: List[Dict],
    existing_results: Dict[str, Dict]
) -> Tuple[List[str], List[str]]:
    youtube_retry = []
    web_retry = []

    for kw_dict in all_keywords:
        keyword = kw_dict['keyword']
        existing = existing_results.get(keyword, {})

        youtube_data = existing.get('youtube', {})
        if youtube_data.get('count', 0) == 0 or len(youtube_data.get('items', [])) == 0:
            youtube_retry.append(keyword)

        web_data = existing.get('web', {})
        if web_data.get('count', 0) == 0 or len(web_data.get('items', [])) == 0:
            web_retry.append(keyword)

    return youtube_retry, web_retry


def merge_results(
    all_keywords: List[Dict],
    existing_results: Dict[str, Dict],
    youtube_new: Dict[str, List],
    web_new: Dict[str, List]
) -> List[Dict]:
    merged = []

    for kw_dict in all_keywords:
        keyword = kw_dict['keyword']
        category = kw_dict.get('category', '')

        existing = existing_results.get(keyword, {})
        # Preserve category from existing or from input
        if not category:
            category = existing.get('category', '')

        existing_youtube = existing.get('youtube', {'count': 0, 'items': []})
        existing_web = existing.get('web', {'count': 0, 'items': []})

        new_youtube = youtube_new.get(keyword, [])
        new_web = web_new.get(keyword, [])

        final_youtube = {
            'count': len(new_youtube),
            'items': [item.to_dict() for item in new_youtube]
        } if new_youtube else existing_youtube

        final_web = {
            'count': len(new_web),
            'items': [item.to_dict() for item in new_web]
        } if new_web else existing_web

        merged.append({
            'keyword': keyword,
            'category': category,
            'youtube': final_youtube,
            'web': final_web
        })

    return merged


async def search_with_retry(
    search_func,
    keywords: List[str],
    source_name: str,
    max_retries: int = None,
    retry_delay: int = None
) -> Dict[str, List]:
    if not keywords:
        return {}

    if max_retries is None:
        max_retries = Config.SEARCH_MAX_RETRIES
    if retry_delay is None:
        retry_delay = Config.SEARCH_RETRY_DELAY

    results = {}
    failed_keywords = keywords.copy()

    for attempt in range(1, max_retries + 1):
        if not failed_keywords:
            break

        print(f"\n{source_name} attempt {attempt}: {len(failed_keywords)} keywords")

        batch_results = await search_func(failed_keywords)

        new_failed = []
        for keyword in failed_keywords:
            items = batch_results.get(keyword, [])
            if items:
                results[keyword] = items
                print(f"  ✓ {keyword}: {len(items)} results")
            else:
                new_failed.append(keyword)
                if attempt < max_retries:
                    print(f"  ✗ {keyword}: no results, will retry")
                else:
                    print(f"  ✗ {keyword}: no results after {max_retries} retries")

        failed_keywords = new_failed

        if failed_keywords and attempt < max_retries:
            print(f"  Waiting {retry_delay}s before retry...")
            await asyncio.sleep(retry_delay)

    success_count = len(results)
    failed_count = len(failed_keywords)
    print(f"\n{source_name} search done:")
    print(f"  - Success: {success_count}")
    if failed_count > 0:
        print(f"  - Failed:  {failed_count} (after {max_retries} retries)")

    return results


async def run_search(project: str, keywords_file: str):
    """Run the collect step programmatically."""
    Config.init(project)

    print("=" * 70)
    print(f"  Step 1: Search [{project}]")
    print("=" * 70)

    if not Config.validate():
        print("\n⚠️  Config incomplete, continuing anyway")

    Config.print_summary()

    keywords = load_keywords_from_json(keywords_file)

    if not keywords:
        print("❌ No keywords found")
        return

    # Overlay categories from the classify step's cache (if present), without
    # clobbering any category already set manually via "categories".
    classified_path = f"{Config.OUT_DIR}/classified_keywords.json"
    if os.path.exists(classified_path):
        try:
            classified = load_json(classified_path)
            cat_by_kw = {c['keyword']: c['category'] for c in classified}
            overlaid = 0
            for kw in keywords:
                if not kw['category'] and kw['keyword'] in cat_by_kw:
                    kw['category'] = cat_by_kw[kw['keyword']]
                    overlaid += 1
            if overlaid:
                print(f"🏷️  Applied {overlaid} categories from classify cache")
        except Exception as e:
            print(f"⚠️  Failed to load classified_keywords.json: {e}")

    # Extract keyword strings and detect categories
    keyword_strings = [kw['keyword'] for kw in keywords]
    categories = set(kw['category'] for kw in keywords if kw['category'])

    # Read game_name / filter_keyword
    game_name = ''
    filter_keyword = ''
    try:
        with open(keywords_file, 'r', encoding='utf-8') as f:
            kw_raw = json.load(f)
        game_name = kw_raw.get('game_name', '').strip()
        filter_keyword = kw_raw.get('filter_keyword', '').strip() or game_name
        if filter_keyword:
            print(f"🏷️  Filter keyword: {filter_keyword}")
    except Exception:
        pass

    print(f"📋 Keywords: {len(keywords)}")
    if categories:
        print(f"📂 Categories: {', '.join(sorted(categories))}")

    existing_results = load_existing_results()
    youtube_retry, web_retry = filter_keywords_for_retry(keywords, existing_results)

    print(f"\n📊 Retry stats:")
    print(f"  - Total:          {len(keyword_strings)}")
    print(f"  - YouTube retry:  {len(youtube_retry)}")
    print(f"  - Web retry:      {len(web_retry)}")
    print(f"  - YouTube cached: {len(keyword_strings) - len(youtube_retry)}")
    print(f"  - Web cached:     {len(keyword_strings) - len(web_retry)}")

    yt = YouTube()
    web = Web()

    yt_results = {}
    web_results = {}

    if youtube_retry or web_retry:
        print("\n" + "=" * 70)
        print("  Starting search (with auto-retry)")
        print("=" * 70)

        async def yt_search_with_filter(kws):
            return await yt.search_batch(kws, filter_keyword=filter_keyword)

        async def web_search_with_filter(kws):
            return await web.search_batch(kws, filter_keyword=filter_keyword)

        yt_results, web_results = await asyncio.gather(
            search_with_retry(yt_search_with_filter, youtube_retry, "YouTube"),
            search_with_retry(web_search_with_filter, web_retry, "Web")
        )
    else:
        print("\n✅ All keywords already have results, skipping search")

    keyword_data = merge_results(keywords, existing_results, yt_results, web_results)

    pending = {
        "version": "2.0",
        "created_at": datetime.now().isoformat(),
        "keywords": keyword_data
    }

    output_file = f"{Config.OUT_DIR}/search_results.json"
    ensure_dir(Config.OUT_DIR)
    save_json(pending, output_file)

    total_yt = sum(kw['youtube']['count'] for kw in keyword_data)
    total_web = sum(kw['web']['count'] for kw in keyword_data)

    print("\n" + "=" * 70)
    print("  ✅ Search complete")
    print("=" * 70)
    print(f"YouTube: {total_yt} videos")
    print(f"Web:    {total_web} pages")
    print(f"Output: {output_file}")
    print("\nNext steps:")
    print("  1. Review search_results.json")
    print("  2. Set 'selected': false to exclude items")
    print(f"  3. Run: seoscout extract --project {project}")
    print("=" * 70)


async def main():
    parser = argparse.ArgumentParser(description="Step 1: Search & collect metadata")
    parser.add_argument("--project", "--domain", required=True,
                        help="Project name for data isolation")
    parser.add_argument("--keywords", "--json", required=True,
                        help="Path to keywords JSON file")
    args = parser.parse_args()

    await run_search(args.project, args.keywords)


if __name__ == "__main__":
    asyncio.run(main())
