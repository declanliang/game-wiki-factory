from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .classifier import Candidate, add_candidate, canonical, classify, normalize_keyword


SIMILARWEB_NAMES = ("similarweb.csv",)
GOOGLE_SUGGEST_NAMES = ("google-suggest.txt", "google_suggest.txt")
TRENDS_TOP_GLOB = "searched_with_top-searches_*.csv"
TRENDS_RISING_GLOB = "searched_with_rising-searches_*.csv"
KEYWORD_HEADERS = {
    "keyword",
    "keywords",
    "query",
    "search term",
    "search keyword",
    "关键词",
    "關鍵詞",
}


def google_suggest_path(input_dir: Path) -> Path | None:
    return next(
        (input_dir / name for name in GOOGLE_SUGGEST_NAMES if (input_dir / name).exists()),
        None,
    )


def _read_csv_keywords(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        rows = list(reader)
    if not rows:
        return []
    header = [canonical(value) if value not in {"关键词", "關鍵詞"} else value for value in rows[0]]
    index = next((i for i, value in enumerate(header) if value in KEYWORD_HEADERS), None)
    if index is None:
        if len(rows[0]) != 1:
            raise ValueError(
                f"{path.name} must contain a keyword/关键词 column; found: {rows[0]}"
            )
        index = 0
        data_rows = rows
    else:
        data_rows = rows[1:]
    return [row[index].strip() for row in data_rows if len(row) > index and row[index].strip()]


def _read_text_keywords(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _read_trends_rows(path: Path) -> list[tuple[str, float]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        output: list[tuple[str, float]] = []
        for row in rows:
            query = str(row.get("query") or "").strip()
            if not query:
                continue
            try:
                interest = float(str(row.get("search interest") or 0).replace(",", ""))
            except ValueError:
                interest = 0
            output.append((query, interest))
        return output


def _candidates_from_values(
    topic: str,
    values: list[str],
    source: str,
) -> tuple[list[Candidate], list[dict[str, str]]]:
    store: dict[str, Candidate] = {}
    rejected: list[dict[str, str]] = []
    for raw in values:
        keyword = normalize_keyword(raw, topic)
        if not keyword:
            rejected.append({"keyword": raw, "source": source, "reason": "core, invalid, or risky"})
            continue
        add_candidate(
            store,
            Candidate(keyword=keyword, sources={source}, evidence=[raw]),
        )
    return list(store.values()), rejected


def load_manual_inputs(
    topic: str,
    input_dir: Path,
) -> tuple[list[Candidate], list[dict[str, str]], dict[str, Any]]:
    candidates: list[Candidate] = []
    rejected: list[dict[str, str]] = []
    files: list[dict[str, Any]] = []

    for name in SIMILARWEB_NAMES:
        path = input_dir / name
        if not path.exists():
            continue
        values = _read_csv_keywords(path)
        accepted, invalid = _candidates_from_values(topic, values, "similarweb")
        candidates.extend(accepted)
        rejected.extend(invalid)
        files.append(
            {
                "file": name,
                "source": "similarweb",
                "raw_keywords": len(values),
                "accepted_keywords": len(accepted),
                "rejected_keywords": len(invalid),
            }
        )

    for pattern, source, signal in (
        (TRENDS_TOP_GLOB, "google_trends_manual_top", "trends_top"),
        (TRENDS_RISING_GLOB, "google_trends_manual_rising", "trends_rising"),
    ):
        for path in sorted(input_dir.glob(pattern)):
            rows = _read_trends_rows(path)
            accepted: list[Candidate] = []
            invalid: list[dict[str, str]] = []
            for raw, interest in rows:
                items, rejected_items = _candidates_from_values(topic, [raw], source)
                for item in items:
                    setattr(item, signal, interest)
                    item.finish()
                accepted.extend(items)
                invalid.extend(rejected_items)
            candidates.extend(accepted)
            rejected.extend(invalid)
            files.append(
                {
                    "file": path.name,
                    "source": source,
                    "raw_keywords": len(rows),
                    "accepted_keywords": len(accepted),
                    "rejected_keywords": len(invalid),
                }
            )

    suggest_path = google_suggest_path(input_dir)
    if suggest_path:
        values = _read_text_keywords(suggest_path)
        accepted, invalid = _candidates_from_values(topic, values, "google_suggest_manual")
        candidates.extend(accepted)
        rejected.extend(invalid)
        files.append(
            {
                "file": suggest_path.name,
                "source": "google_suggest_manual",
                "raw_keywords": len(values),
                "accepted_keywords": len(accepted),
                "rejected_keywords": len(invalid),
            }
        )

    return candidates, rejected, {
        "directory": str(input_dir),
        "files": files,
        "raw_keywords": sum(int(item["raw_keywords"]) for item in files),
        "accepted_keywords": sum(int(item["accepted_keywords"]) for item in files),
        "rejected_keywords": sum(int(item["rejected_keywords"]) for item in files),
    }


def merge_manual_candidates(
    topic: str,
    automatic: list[Candidate],
    manual: list[Candidate],
) -> list[Candidate]:
    store = {canonical(item.keyword): item for item in automatic}
    for item in manual:
        add_candidate(store, item)
    merged = list(store.values())
    for item in merged:
        item.category = classify(item.keyword, topic)
        item.finish()
    merged.sort(key=lambda item: (-item.score, item.keyword))
    return merged
