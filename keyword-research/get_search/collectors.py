from __future__ import annotations

import string
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .client import DataForSEOClient
from .config import Settings


LABS_ENDPOINT = "/v3/dataforseo_labs/google/keyword_suggestions/live"
TRENDS_ENDPOINT = "/v3/keywords_data/google_trends/explore/live"
AUTOCOMPLETE_ENDPOINT = "/v3/serp/google/autocomplete/live/advanced"
GOOGLE_SUGGEST_ENDPOINT = "https://suggestqueries.google.com/complete/search"
YOUTUBE_ENDPOINT = "/v3/serp/youtube/organic/live/advanced"


def collect_labs(client: DataForSEOClient, topic: str, settings: Settings) -> dict[str, Any]:
    call = client.post(
        LABS_ENDPOINT,
        {
            "keyword": topic,
            "location_name": settings.location,
            "language_code": settings.language,
            "include_seed_keyword": True,
            "include_serp_info": False,
            "include_clickstream_data": False,
            "ignore_synonyms": False,
            "order_by": ["keyword_info.search_volume,desc"],
            "limit": settings.labs_limit,
        },
    )
    return {"endpoint": call.endpoint, "cost": call.cost, "response": call.response}


def collect_trends(client: DataForSEOClient, topic: str, settings: Settings) -> dict[str, Any]:
    call = client.post(
        TRENDS_ENDPOINT,
        {
            "keywords": [topic],
            "location_name": settings.location,
            "language_code": settings.language,
            "time_range": "past_7_days",
            "type": "web",
        },
    )
    return {"endpoint": call.endpoint, "cost": call.cost, "response": call.response}


def collect_autocomplete(
    client: DataForSEOClient,
    topic: str,
    settings: Settings,
    include_az: bool,
) -> dict[str, Any]:
    queries = [topic]
    if include_az:
        queries.extend(f"{topic} {letter}" for letter in string.ascii_lowercase)

    def fetch(query: str) -> dict[str, Any]:
        try:
            call = client.post(
                AUTOCOMPLETE_ENDPOINT,
                {
                    "keyword": query,
                    "location_name": settings.location,
                    "language_code": settings.language,
                    "client": "chrome",
                },
            )
            return {
                "query": query,
                "cost": call.cost,
                "response": call.response,
                "error": None,
            }
        except Exception as exc:  # Individual prefixes are allowed to degrade.
            if "task 40102" in str(exc) and "No Search Results" in str(exc):
                return {
                    "query": query,
                    "cost": 0.0,
                    "response": None,
                    "error": None,
                    "empty_reason": "No Search Results",
                }
            return {"query": query, "cost": 0.0, "response": None, "error": str(exc)}

    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fetch, query): query for query in queries}
        for future in as_completed(futures):
            records.append(future.result())
    records.sort(key=lambda record: queries.index(record["query"]))
    return {
        "endpoint": AUTOCOMPLETE_ENDPOINT,
        "cost": round(sum(float(record["cost"]) for record in records), 6),
        "queries": records,
    }


def collect_google_suggest(
    topic: str,
    settings: Settings,
    include_az: bool,
) -> dict[str, Any]:
    queries = [topic]
    if include_az:
        queries.extend(f"{topic} {letter}" for letter in string.ascii_lowercase)

    records: list[dict[str, Any]] = []
    for query in queries:
        url = GOOGLE_SUGGEST_ENDPOINT + "?" + urllib.parse.urlencode(
            {"client": "firefox", "q": query, "hl": settings.language}
        )
        error: str | None = None
        suggestions: list[dict[str, Any]] = []
        for attempt in range(3):
            try:
                request = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 get-search/1.0"},
                )
                with urllib.request.urlopen(request, timeout=settings.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                values = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
                suggestions = [
                    {"suggestion": str(value), "rank_absolute": rank}
                    for rank, value in enumerate(values, 1)
                    if str(value).strip()
                ]
                error = None
                break
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                error = str(exc)
                if attempt < 2:
                    time.sleep(0.5 * (2**attempt))
        records.append(
            {"query": query, "url": url, "suggestions": suggestions, "error": error}
        )
        time.sleep(0.1)

    if not any(record["suggestions"] for record in records):
        raise RuntimeError("Google Suggest returned no suggestions for all queries")
    unique_suggestions: list[str] = []
    seen: set[str] = set()
    for record in records:
        for item in record["suggestions"]:
            value = str(item["suggestion"]).strip()
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                unique_suggestions.append(value)
    return {
        "source": "google-direct",
        "endpoint": GOOGLE_SUGGEST_ENDPOINT,
        "cost": 0.0,
        "queries": records,
        "unique_suggestions": unique_suggestions,
    }


def collect_youtube(client: DataForSEOClient, topic: str, settings: Settings) -> dict[str, Any]:
    call = client.post(
        YOUTUBE_ENDPOINT,
        {
            "keyword": topic,
            "location_name": settings.location,
            "language_code": settings.language,
            "device": "desktop",
            "block_depth": settings.youtube_depth,
        },
    )
    return {"endpoint": call.endpoint, "cost": call.cost, "response": call.response}
