from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .client import first_task_results


RISK_PATTERN = re.compile(
    r"\b(script|scripts|hack|hacks|exploit|exploits|executor|inject|injection|"
    r"pastebin|macro|macros|auto\s*farm|auto\s*quest|auto\s*egg|no\s*key|"
    r"inf(?:inite)?\s*money|cheat|dupe|account\s+for\s+sale|buy\s+account)\b",
    re.IGNORECASE,
)

FOREIGN_QUERY_PATTERN = re.compile(
    r"\b(khi nao|ra mat|ngay ra mat|quando lanca|lancamento|data de lancamento|codigo de|codigos de)\b",
    re.IGNORECASE,
)

CATEGORY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("codes", re.compile(r"\b(code|codes|redeem)\b", re.I)),
    ("tier-list", re.compile(r"\b(tier\s*list|ranking|rankings|best)\b", re.I)),
    ("units", re.compile(r"\b(unit|units|trait|traits|mythic|starter|evolve|evolution|meta)\b", re.I)),
    ("anomalies", re.compile(r"\b(anomaly|anomalies|ghost|jumpscare|stalker|secret|secrets)\b", re.I)),
    ("characters", re.compile(r"\b(character|characters|class|classes|intern|secretary)\b", re.I)),
    ("jobs", re.compile(r"\b(job|jobs|role|roles|doctor|nurse|vet|veterinarian|staff)\b", re.I)),
    ("money", re.compile(r"\b(money|cash|coin|coins|gem|gems|currency|earn|rich)\b", re.I)),
    ("locations", re.compile(r"\b(map|maps|location|locations|where|hospital|room|rooms)\b", re.I)),
    ("updates", re.compile(r"\b(update|updates|release|event|events|new|version|early access|coming out)\b", re.I)),
    ("modes", re.compile(r"\b(mode|modes|expedition|expeditions|time chamber|raid|raids|boss|bosses|story)\b", re.I)),
    ("enemies", re.compile(r"\b(enemy|enemies|monster|monsters|mob|mobs)\b", re.I)),
    ("upgrades", re.compile(r"\b(upgrade|upgrades|build|builds)\b", re.I)),
    ("floors", re.compile(r"\b(floor|floors|level|levels)\b", re.I)),
    ("servers", re.compile(r"\b(server|servers|discord|reddit|community|private)\b", re.I)),
    ("items", re.compile(r"\b(item|items|tool|tools|equipment|weapon|weapons|key|keys|utility)\b", re.I)),
    ("animals", re.compile(r"\b(animal|animals|pet|pets|dog|dogs|cat|cats|horse|horses)\b", re.I)),
    ("quests", re.compile(r"\b(quest|quests|mission|missions|badge|badges)\b", re.I)),
]

YOUTUBE_PHRASES = re.compile(
    r"\b(?:active codes?|codes?|beginner guide|complete guide|ultimate guide|full guide|guide|tips? and tricks?|"
    r"how to (?:play|get|find|unlock|earn|make|use) [a-z0-9 ]{1,40}?|"
    r"best [a-z0-9 ]{1,30}?|tier list|updates?|release date|gamepass(?:es)?|"
    r"animals?|pets?|jobs?|doctor|nurse|vet|money|cash|coins?|gems?|maps?|locations?|"
    r"quests?|badges?|private servers?|discord|secrets?|tutorial|walkthrough|full game|"
    r"boss(?:es)?|boss fight|boss battle|floors?|enemies?|monsters?|upgrades?|weapons?|"
    r"loot|survival|how to survive)\b",
    re.I,
)

# YouTube often exposes useful game mechanics before those phrases appear in
# Google Suggest.  These semantic topics are admitted only when at least two
# distinct videos independently mention the same durable player-help intent.
# A single entertainment title can therefore never create one of these pages.
YOUTUBE_STABLE_TOPICS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("juking and movement guide", re.compile(r"\b(?:juke|jukes|juking|movement|breaking ankles?)\b", re.I)),
    ("bomb passing techniques", re.compile(r"\b(?:bomb pass(?:ing)?|pass(?:ing)? the bomb|passing techniques?)\b", re.I)),
    (
        "map positioning guide",
        re.compile(r"\b(?:(?:map|arena) (?:positioning|strategy|strategies|tips)|tips (?:and tricks )?(?:for|on) (?:specific )?maps?)\b", re.I),
    ),
)
YOUTUBE_STABLE_TOPIC_MIN_VIDEOS = 2

ENTITY_CATEGORIES = {"characters", "units", "enemies", "bosses", "weapons", "items", "modes", "quests"}


def page_type_for_category(category: str) -> str:
    normalized = canonical(category).replace(" ", "-")
    if normalized == "codes":
        return "codes"
    if normalized == "tier-list":
        return "tier_list"
    if normalized == "updates":
        return "update"
    if normalized in ENTITY_CATEGORIES:
        return "entity"
    return "guide"


def ascii_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-zA-Z0-9' ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def canonical(value: str) -> str:
    return ascii_text(value).lower()


def parse_number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").lower().replace(",", "").replace("%", "").strip()
    if text == "breakout":
        return 5000.0
    try:
        return float(text)
    except ValueError:
        return 0.0


@dataclass
class Candidate:
    keyword: str
    sources: set[str] = field(default_factory=set)
    labs_search_volume: int = 0
    labs_monthly_searches: list[dict[str, Any]] = field(default_factory=list)
    labs_core_keyword: str | None = None
    search_intent: str | None = None
    autocomplete_best_rank: int | None = None
    autocomplete_occurrences: int = 0
    trends_top: float = 0
    trends_rising: float = 0
    youtube_views: int = 0
    youtube_occurrences: int = 0
    evidence: list[str] = field(default_factory=list)
    category: str = "guide"
    score: float = 0
    page_type: str = "guide"
    entity_name: str | None = None
    entity_type: str | None = None
    intent: str = ""
    confidence: float | None = None
    evidence_urls: list[str] = field(default_factory=list)

    def merge(self, other: "Candidate") -> None:
        self.sources.update(other.sources)
        self.labs_search_volume = max(self.labs_search_volume, other.labs_search_volume)
        if other.labs_monthly_searches:
            self.labs_monthly_searches = other.labs_monthly_searches
        self.labs_core_keyword = self.labs_core_keyword or other.labs_core_keyword
        self.search_intent = self.search_intent or other.search_intent
        if other.autocomplete_best_rank is not None:
            self.autocomplete_best_rank = min(
                rank for rank in (self.autocomplete_best_rank, other.autocomplete_best_rank) if rank is not None
            )
        self.autocomplete_occurrences += other.autocomplete_occurrences
        self.trends_top = max(self.trends_top, other.trends_top)
        self.trends_rising = max(self.trends_rising, other.trends_rising)
        self.youtube_views += other.youtube_views
        self.youtube_occurrences += other.youtube_occurrences
        self.evidence = list(dict.fromkeys(self.evidence + other.evidence))[:10]
        if other.page_type != "guide" or self.page_type == "guide":
            self.page_type = other.page_type
        self.entity_name = self.entity_name or other.entity_name
        self.entity_type = self.entity_type or other.entity_type
        self.intent = self.intent or other.intent
        if other.confidence is not None:
            self.confidence = max(self.confidence or 0, other.confidence)
        self.evidence_urls = list(dict.fromkeys(self.evidence_urls + other.evidence_urls))[:10]

    def finish(self) -> None:
        score = 0.0
        if self.labs_search_volume:
            score += 80 + math.log10(self.labs_search_volume + 1) * 18
        score += len(self.sources) * 24
        score += self.autocomplete_occurrences * 8
        if self.autocomplete_best_rank:
            score += max(0, 18 - self.autocomplete_best_rank)
        score += min(45, self.trends_top * 0.35)
        score += min(55, math.log10(self.trends_rising + 1) * 14) if self.trends_rising else 0
        score += min(55, math.log10(self.youtube_views + 1) * 8) if self.youtube_views else 0
        score += min(20, self.youtube_occurrences * 4)
        self.score = round(score, 3)

    def as_dict(self) -> dict[str, Any]:
        return {
            "keyword": self.keyword,
            "category": self.category,
            "score": self.score,
            "sources": sorted(self.sources),
            "metrics": {
                "labs_search_volume": self.labs_search_volume,
                "labs_monthly_searches": self.labs_monthly_searches,
                "labs_core_keyword": self.labs_core_keyword,
                "search_intent": self.search_intent,
                "autocomplete_best_rank": self.autocomplete_best_rank,
                "autocomplete_occurrences": self.autocomplete_occurrences,
                "trends_top": self.trends_top,
                "trends_rising": self.trends_rising,
                "youtube_views": self.youtube_views,
                "youtube_occurrences": self.youtube_occurrences,
            },
            "evidence": self.evidence,
            "pageType": self.page_type,
            "entityName": self.entity_name,
            "entityType": self.entity_type,
            "intent": self.intent,
            "confidence": self.confidence,
            "evidenceUrls": self.evidence_urls,
        }


def normalize_keyword(raw: str, topic: str, allow_unprefixed: bool = False) -> str | None:
    value = canonical(raw)
    topic_key = canonical(topic)
    if not value or RISK_PATTERN.search(value) or FOREIGN_QUERY_PATTERN.search(value):
        return None
    if value == topic_key:
        return None
    if topic_key in value:
        tail = re.sub(rf"\b{re.escape(topic_key)}\b", " ", value, count=1)
        tail = re.sub(r"\s+", " ", tail).strip()
    else:
        platform_tokens = {"roblox", "steam"}
        core_tokens = [token for token in topic_key.split() if token not in platform_tokens]
        core = " ".join(core_tokens)
        platform = next((token for token in topic_key.split() if token in platform_tokens), None)
        starts_core = bool(core) and (value == core or value.startswith(f"{core} "))
        starts_platform_core = bool(platform and core) and value.startswith(f"{platform} {core}")
        if starts_core and platform and re.search(rf"\b{platform}\b", value):
            tail = value[len(core) :].strip()
            tail = re.sub(rf"\b{platform}\b", " ", tail, count=1)
            tail = re.sub(r"\s+", " ", tail).strip()
        elif starts_platform_core:
            tail = value[len(f"{platform} {core}") :].strip()
        elif allow_unprefixed:
            tail = value
        else:
            return None
    if not tail or tail in {"roblox", "steam", "game", "wiki", "official"}:
        return None
    tail = re.sub(r"\bwiki\b", "", tail)
    tail = re.sub(r"\s+", " ", tail).strip()
    if len(tail) < 2:
        return None
    return f"{topic_key} {tail}"


def add_candidate(store: dict[str, Candidate], candidate: Candidate) -> None:
    key = canonical(candidate.keyword)
    if key in store:
        store[key].merge(candidate)
    else:
        store[key] = candidate


def extract_candidates(topic: str, raw: dict[str, Any]) -> tuple[list[Candidate], list[dict[str, str]]]:
    store: dict[str, Candidate] = {}
    rejected: list[dict[str, str]] = []

    labs_response = raw.get("labs", {}).get("response") or {}
    for result in first_task_results(labs_response):
        records = list(result.get("items") or [])
        if result.get("seed_keyword_data"):
            records.append(result["seed_keyword_data"])
        for item in records:
            raw_keyword = str(item.get("keyword") or "")
            keyword = normalize_keyword(raw_keyword, topic)
            if not keyword:
                rejected.append({"keyword": raw_keyword, "reason": "core, invalid, or risky"})
                continue
            info = item.get("keyword_info") or {}
            props = item.get("keyword_properties") or {}
            intent = item.get("search_intent_info") or {}
            add_candidate(
                store,
                Candidate(
                    keyword=keyword,
                    sources={"labs"},
                    labs_search_volume=int(info.get("search_volume") or 0),
                    labs_monthly_searches=info.get("monthly_searches") or [],
                    labs_core_keyword=props.get("core_keyword"),
                    search_intent=intent.get("main_intent"),
                    evidence=[raw_keyword],
                ),
            )

    trends_response = raw.get("trends", {}).get("response") or {}
    for result in first_task_results(trends_response):
        for item in result.get("items") or []:
            if item.get("type") != "google_trends_queries_list":
                continue
            data = item.get("data") or {}
            for trend_type in ("top", "rising"):
                for entry in data.get(trend_type) or []:
                    raw_keyword = str(entry.get("query") or "")
                    keyword = normalize_keyword(raw_keyword, topic, allow_unprefixed=True)
                    if not keyword:
                        rejected.append({"keyword": raw_keyword, "reason": "core, invalid, or risky"})
                        continue
                    candidate = Candidate(keyword=keyword, sources={"trends"}, evidence=[raw_keyword])
                    if trend_type == "top":
                        candidate.trends_top = parse_number(entry.get("value"))
                    else:
                        candidate.trends_rising = parse_number(entry.get("value"))
                    add_candidate(store, candidate)

    for query in raw.get("autocomplete", {}).get("queries") or []:
        for item in query.get("suggestions") or []:
            raw_keyword = str(item.get("suggestion") or "")
            keyword = normalize_keyword(raw_keyword, topic)
            if not keyword:
                if raw_keyword:
                    rejected.append({"keyword": raw_keyword, "reason": "core, invalid, or risky"})
                continue
            add_candidate(
                store,
                Candidate(
                    keyword=keyword,
                    sources={"autocomplete"},
                    autocomplete_best_rank=int(item.get("rank_absolute") or 999),
                    autocomplete_occurrences=1,
                    evidence=[raw_keyword],
                ),
            )
        response = query.get("response") or {}
        for result in first_task_results(response):
            for item in result.get("items") or []:
                raw_keyword = str(item.get("suggestion") or "")
                keyword = normalize_keyword(raw_keyword, topic)
                if not keyword:
                    if raw_keyword:
                        rejected.append({"keyword": raw_keyword, "reason": "core, invalid, or risky"})
                    continue
                add_candidate(
                    store,
                    Candidate(
                        keyword=keyword,
                        sources={"autocomplete"},
                        autocomplete_best_rank=int(item.get("rank_absolute") or 999),
                        autocomplete_occurrences=1,
                        evidence=[raw_keyword],
                    ),
                )

    youtube_response = raw.get("youtube", {}).get("response") or {}
    stable_topic_evidence: dict[str, list[tuple[str, int]]] = defaultdict(list)
    same_game_videos: dict[str, tuple[str, int]] = {}
    topic_tokens = {
        token[:-1] if token.endswith("s") and len(token) > 4 else token
        for token in canonical(topic).split()
        if token not in {"roblox", "steam", "game", "the", "a", "an"}
    }
    platform_token = next((token for token in canonical(topic).split() if token in {"roblox", "steam"}), None)
    for result in first_task_results(youtube_response):
        for item in result.get("items") or []:
            if item.get("type") != "youtube_video":
                continue
            title = canonical(str(item.get("title") or ""))
            views = int(item.get("views_count") or 0)
            original_title = str(item.get("title") or "")
            title_tokens = {
                token[:-1] if token.endswith("s") and len(token) > 4 else token
                for token in title.split()
            }
            if topic_tokens and topic_tokens.issubset(title_tokens) and (
                platform_token != "roblox" or "roblox" in title_tokens
            ):
                same_game_videos[title] = (original_title, views)
            for topic_tail, pattern in YOUTUBE_STABLE_TOPICS:
                if pattern.search(title):
                    stable_topic_evidence[topic_tail].append((original_title, views))
            seen_phrases: set[str] = set()
            for match in YOUTUBE_PHRASES.finditer(title):
                phrase = re.sub(r"\s+", " ", match.group(0)).strip()
                if not phrase or phrase in seen_phrases:
                    continue
                seen_phrases.add(phrase)
                if re.search(r"\b(tiktok|youtube|shorts?|video|gameplay|roblox|steam|reaction)\b", phrase):
                    continue
                if phrase.startswith("best ") and not re.search(
                    r"\b(unit|units|team|teams|trait|traits|mythic|starter|character|characters|meta|evolution)\b",
                    phrase,
                ):
                    continue
                if phrase in {"secret", "best", "guide"} or re.search(
                    r"\b(before|after|with|for|the|a|an|in|on|at|to)$", phrase
                ):
                    continue
                keyword = normalize_keyword(phrase, topic, allow_unprefixed=True)
                if not keyword:
                    continue
                add_candidate(
                    store,
                    Candidate(
                        keyword=keyword,
                        sources={"youtube"},
                        youtube_views=views,
                        youtube_occurrences=1,
                        evidence=[str(item.get("title") or "")],
                    ),
                )

    for topic_tail, records in stable_topic_evidence.items():
        distinct: dict[str, int] = {}
        for title, views in records:
            distinct[canonical(title)] = max(views, distinct.get(canonical(title), 0))
        if len(distinct) < YOUTUBE_STABLE_TOPIC_MIN_VIDEOS:
            continue
        keyword = normalize_keyword(topic_tail, topic, allow_unprefixed=True)
        if not keyword:
            continue
        add_candidate(
            store,
            Candidate(
                keyword=keyword,
                sources={"youtube"},
                youtube_views=sum(distinct.values()),
                youtube_occurrences=len(distinct),
                evidence=[title for title, _ in records[:10]],
            ),
        )

    # Very new games may have no Suggest suffixes yet while several independent
    # videos clearly cover the exact Roblox experience. In that narrow case a
    # general guide is supported by multi-video same-game evidence, not invented
    # as a zero-evidence fallback.
    if len(same_game_videos) >= 3:
        records = list(same_game_videos.values())
        add_candidate(
            store,
            Candidate(
                keyword=f"{canonical(topic)} guide",
                sources={"youtube"},
                youtube_views=sum(views for _title, views in records),
                youtube_occurrences=len(records),
                evidence=[title for title, _views in records[:10]],
            ),
        )

    candidates = list(store.values())
    for candidate in candidates:
        candidate.category = classify(candidate.keyword, topic)
        candidate.page_type = page_type_for_category(candidate.category)
        candidate.finish()
    candidates.sort(key=lambda item: (-item.score, item.keyword))
    return candidates, rejected


def classify(keyword: str, topic: str) -> str:
    tail = canonical(keyword).removeprefix(canonical(topic)).strip()
    for category, pattern in CATEGORY_PATTERNS:
        if pattern.search(tail):
            return category
    return "guide"


def select_keywords(candidates: list[Candidate], maximum: int = 40) -> list[Candidate]:
    allowed_categories = {"guide"}
    if any(candidate.category == "codes" for candidate in candidates):
        allowed_categories.add("codes")
    for candidate in candidates:
        if len(allowed_categories) >= 8:
            break
        allowed_categories.add(candidate.category)

    selected: list[Candidate] = []
    codes_used = False
    seen_weak: set[str] = set()
    for candidate in candidates:
        if candidate.category not in allowed_categories:
            continue
        if candidate.category == "codes":
            if codes_used:
                continue
            codes_used = True
        weak = re.sub(r"\b(a|an|the|for|in|on|roblox|steam)\b", "", canonical(candidate.keyword))
        weak = re.sub(r"\b([a-z]+)ies\b", r"\1y", weak)
        weak = re.sub(r"\b([a-z]+)s\b", r"\1", weak)
        weak = re.sub(r"\s+", " ", weak).strip()
        if weak in seen_weak:
            continue
        seen_weak.add(weak)
        selected.append(candidate)
        if len(selected) >= maximum:
            break

    categories = defaultdict(list)
    for candidate in selected:
        categories[candidate.category].append(candidate)
    if "guide" not in categories:
        guide_candidate = next((item for item in candidates if item.category == "guide" and item not in selected), None)
        if guide_candidate:
            if len(selected) >= maximum:
                selected[-1] = guide_candidate
            else:
                selected.append(guide_candidate)
    return selected


def build_keywords_json(topic: str, selected: list[Candidate]) -> dict[str, Any]:
    grouped: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in selected:
        grouped[candidate.category].append(candidate)

    ordered_categories = sorted(
        grouped,
        key=lambda name: (0 if name == "guide" else 1, -max(item.score for item in grouped[name]), name),
    )[:8]
    return {
        "topic_name": canonical(topic),
        "categories": [
            {
                "category": category,
                "keywords": [item.keyword for item in sorted(grouped[category], key=lambda item: -item.score)],
                "topics": [
                    {
                        "keyword": item.keyword,
                        "pageType": item.page_type,
                        "entityName": item.entity_name,
                        "entityType": item.entity_type,
                        "intent": item.intent,
                        "confidence": item.confidence,
                        "discoverySources": sorted(item.sources),
                        "evidenceUrls": item.evidence_urls,
                    }
                    for item in sorted(grouped[category], key=lambda item: -item.score)
                ],
            }
            for category in ordered_categories
        ],
    }


def validate_keywords(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    topic = str(data.get("topic_name") or "")
    categories = data.get("categories") or []
    if len(categories) > 8:
        errors.append("more than 8 categories")
    all_keywords: list[str] = []
    for category in categories:
        name = str(category.get("category") or "")
        if " " in name and name != "tier list":
            errors.append(f"invalid category name: {name}")
        if name in {"wiki", "gameplay", "general"}:
            errors.append(f"forbidden category: {name}")
        keywords = category.get("keywords") or []
        topics = category.get("topics") or []
        if topics and [item.get("keyword") for item in topics] != keywords:
            errors.append(f"topic metadata does not match keywords for category: {name}")
        if name == "codes" and len(keywords) > 1:
            errors.append("codes contains more than one keyword")
        for keyword in keywords:
            if not str(keyword).startswith(f"{topic} "):
                errors.append(f"keyword does not start with topic: {keyword}")
            if not str(keyword).isascii():
                errors.append(f"non-ASCII keyword: {keyword}")
            if RISK_PATTERN.search(str(keyword)):
                errors.append(f"risky keyword: {keyword}")
            all_keywords.append(str(keyword))
    if len(all_keywords) > 40:
        errors.append("more than 40 keywords")
    if len(set(all_keywords)) != len(all_keywords):
        errors.append("duplicate keywords")
    return errors
