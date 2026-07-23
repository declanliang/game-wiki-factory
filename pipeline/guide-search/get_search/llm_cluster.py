from __future__ import annotations

import json
import hashlib
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .classifier import Candidate, canonical, page_type_for_category


TOAPIS_CHAT_URL = "https://toapis.com/v1/chat/completions"
TOAPIS_RESPONSES_URL = "https://toapis.com/v1/responses"
TOAPIS_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) get-search/1.0"
DEFAULT_CONTEXT_MODEL = "gpt-5.3-codex-official"
DEFAULT_CLUSTER_MODEL = "gpt-5.6-terra"
LOW_CONFIDENCE_THRESHOLD = 0.55
CLUSTER_POLICY_VERSION = 5
CONTEXT_POLICY_VERSION = 4
OPPORTUNITY_CONFIDENCE_THRESHOLD = 0.72
TOAPIS_RETRY_ATTEMPTS = 3
TOAPIS_RETRYABLE_HTTP = {408, 425, 429, 500, 502, 503, 504, 520, 522, 524}

FORBIDDEN_STANDALONE = re.compile(
    r"\b(reddit|discord|trello|logo|youtube|game\s*link)\b", re.IGNORECASE
)
FORBIDDEN_CATEGORIES = {"wiki", "gameplay", "general", "servers", "community"}


@dataclass(frozen=True)
class LLMCall:
    model: str
    data: dict[str, Any]
    usage: dict[str, Any]
    cost_usd: float | None
    response_meta: dict[str, Any]


def _schema(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {"name": name, "strict": True, "schema": schema},
    }


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "") for item in content if isinstance(item, dict)
        )
    return str(content or "")


def _parse_json(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
        value = re.sub(r"\s*```$", "", value)
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("ToAPIs response is not a JSON object")
    return parsed


def _request_toapis(
    api_key: str,
    url: str,
    payload: dict[str, Any],
    timeout_seconds: int = 240,
) -> dict[str, Any]:
    encoded_payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error: Exception | None = None
    raw: Any = None
    for attempt in range(1, TOAPIS_RETRY_ATTEMPTS + 1):
        request = urllib.request.Request(
            url,
            data=encoded_payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": TOAPIS_USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            if exc.code not in TOAPIS_RETRYABLE_HTTP:
                raise RuntimeError(f"ToAPIs HTTP {exc.code}: {detail}") from exc
            last_error = RuntimeError(f"ToAPIs HTTP {exc.code}: {detail}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc

        if attempt < TOAPIS_RETRY_ATTEMPTS:
            delay = 2 ** (attempt - 1)
            print(
                f"[warning] ToAPIs transient request failure "
                f"({attempt}/{TOAPIS_RETRY_ATTEMPTS}): {last_error}; "
                f"retrying in {delay}s"
            )
            time.sleep(delay)
    else:
        raise RuntimeError(
            f"ToAPIs request failed after {TOAPIS_RETRY_ATTEMPTS} attempts: "
            f"{last_error}"
        ) from last_error

    if not isinstance(raw, dict):
        raise RuntimeError("ToAPIs returned a non-object response")
    return raw


def _call_toapis_chat(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    response_format: dict[str, Any],
    *,
    reasoning_effort: str = "medium",
    max_tokens: int = 12000,
    timeout_seconds: int = 240,
) -> LLMCall:
    raw = _request_toapis(
        api_key,
        TOAPIS_CHAT_URL,
        {
            "model": model,
            "messages": messages,
            "response_format": response_format,
            "reasoning_effort": reasoning_effort,
            "max_completion_tokens": max_tokens,
        },
        timeout_seconds,
    )
    choices = raw.get("choices") or []
    if not choices:
        raise RuntimeError(f"ToAPIs returned no choices: {raw.get('error') or 'unknown error'}")
    message = choices[0].get("message") or {}
    data = _parse_json(_content_text(message.get("content")))
    usage = raw.get("usage") or {}
    meta = {
        "id": raw.get("id"),
        "model": raw.get("model") or model,
        "created": raw.get("created"),
        "finish_reason": choices[0].get("finish_reason"),
        "usage": usage,
        "cost_usd": None,
    }
    return LLMCall(model=model, data=data, usage=usage, cost_usd=None, response_meta=meta)


def _responses_text_and_annotations(raw: dict[str, Any]) -> tuple[str, list[Any], list[str]]:
    texts: list[str] = []
    annotations: list[Any] = []
    output_types: list[str] = []
    for item in raw.get("output") or []:
        if not isinstance(item, dict):
            continue
        output_types.append(str(item.get("type") or ""))
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("text"):
                texts.append(str(content["text"]))
            annotations.extend(content.get("annotations") or [])
    return "\n".join(texts), annotations, output_types


def _call_toapis_web_research(
    api_key: str,
    model: str,
    instructions: str,
    input_text: str,
    *,
    max_tokens: int = 7000,
    timeout_seconds: int = 240,
) -> LLMCall:
    payload = {
        "model": model,
        "instructions": instructions,
        "input": input_text,
        "tools": [{"type": "web_search_preview"}],
        "tool_choice": "required",
        "max_output_tokens": max_tokens,
    }

    # A Responses call can succeed at the HTTP level while returning a
    # truncated or otherwise malformed JSON answer. Treat that as a bounded
    # transient provider failure, rather than failing the entire game job.
    raw: dict[str, Any] | None = None
    annotations: list[Any] = []
    output_types: list[str] = []
    last_error: Exception | None = None
    for attempt in range(1, TOAPIS_RETRY_ATTEMPTS + 1):
        raw = _request_toapis(api_key, TOAPIS_RESPONSES_URL, payload, timeout_seconds)
        text, annotations, output_types = _responses_text_and_annotations(raw)
        try:
            if "web_search_call" not in output_types:
                raise RuntimeError("ToAPIs context research completed without a web_search_call")
            if not text:
                raise RuntimeError("ToAPIs Responses API returned no research text")
            data = _parse_json(text)
            break
        except (ValueError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if attempt == TOAPIS_RETRY_ATTEMPTS:
                raise RuntimeError(
                    "ToAPIs context research returned an invalid structured response "
                    f"after {TOAPIS_RETRY_ATTEMPTS} attempts: {exc}"
                ) from exc
            delay = 2 ** (attempt - 1)
            print(
                f"[warning] ToAPIs context response was malformed "
                f"({attempt}/{TOAPIS_RETRY_ATTEMPTS}): {exc}; retrying in {delay}s"
            )
            time.sleep(delay)
    else:  # pragma: no cover - loop always breaks or raises
        raise RuntimeError(f"ToAPIs context research failed: {last_error}")

    assert raw is not None
    usage = raw.get("usage") or {}
    meta = {
        "id": raw.get("id"),
        "model": raw.get("model") or model,
        "status": raw.get("status"),
        "output_types": output_types,
        "web_search_used": True,
        "annotations": annotations,
        "usage": usage,
        "cost_usd": None,
    }
    return LLMCall(model=model, data=data, usage=usage, cost_usd=None, response_meta=meta)


CONTEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "topic": {"type": "string"},
        "game_type": {"type": "string"},
        "release_status": {
            "type": "string",
            "enum": ["pre_release", "early_access", "released", "unknown"],
        },
        "release_date": {"type": ["string", "null"]},
        "summary": {"type": "string"},
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "unit", "trait", "mode", "currency", "item", "map",
                            "boss", "npc", "mechanic", "community", "other",
                        ],
                    },
                    "description": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["name", "type", "description", "confidence"],
            },
        },
        "terminology": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "term": {"type": "string"},
                    "meaning": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["term", "meaning", "confidence"],
            },
        },
        "official_sources": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"url": {"type": "string"}, "type": {"type": "string"}},
                "required": ["url", "type"],
            },
        },
        "page_opportunities": {
            "type": "array",
            "maxItems": 40,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "topic_suffix": {"type": "string"},
                    "page_type": {
                        "type": "string",
                        "enum": ["codes", "tier_list", "update", "entity", "guide"],
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "guide", "progression", "mechanics", "updates", "enemies",
                            "floors", "upgrades", "economy", "bosses", "weapons",
                            "characters", "codes", "tier-list", "modes", "items", "quests"
                        ],
                    },
                    "entity_name": {"type": ["string", "null"]},
                    "entity_type": {"type": ["string", "null"]},
                    "player_intent": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence_urls": {
                        "type": "array",
                        "maxItems": 12,
                        "items": {"type": "string"},
                    },
                    "evidence_types": {
                        "type": "array",
                        "maxItems": 8,
                        "items": {
                            "type": "string",
                            "enum": ["official", "creator", "community", "editorial", "video", "forum"]
                        },
                    },
                    "official_or_creator": {"type": "boolean"},
                },
                "required": [
                    "topic_suffix", "page_type", "category", "entity_name", "entity_type",
                    "player_intent", "confidence", "evidence_urls", "evidence_types",
                    "official_or_creator"
                ],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "topic", "game_type", "release_status", "release_date", "summary",
        "entities", "terminology", "official_sources", "page_opportunities", "warnings",
    ],
}


CLUSTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "topic_name": {"type": "string"},
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "keyword": {"type": "string"},
                    "action": {"type": "string", "enum": ["keep", "merge", "drop"]},
                    "category": {"type": ["string", "null"]},
                    "merge_into": {"type": ["string", "null"]},
                    "entity_type": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string"},
                },
                "required": [
                    "keyword", "action", "category", "merge_into",
                    "entity_type", "confidence", "reason",
                ],
            },
        },
        "category_purposes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category": {"type": "string"},
                    "purpose": {"type": "string"},
                },
                "required": ["category", "purpose"],
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["topic_name", "decisions", "category_purposes", "notes"],
}


def research_game_context(
    api_key: str,
    topic: str,
    candidates: list[Candidate],
    trusted_context: dict[str, Any] | None = None,
    youtube_discovery_evidence: list[dict[str, Any]] | None = None,
    model: str = DEFAULT_CONTEXT_MODEL,
) -> LLMCall:
    focus = [item.keyword for item in candidates[:80]]
    instructions = (
        "You research game terminology for SEO clustering. You must use web search. "
        "Prefer official platform pages, creator-owned sources, and reliable recent community/editorial sources. "
        "Do not use competitor wikis as evidence. Never invent names, dates, mechanics, or URLs. "
        "Separate the game's real concepts from generic video-title language. The output is for a rich "
        "game information site, so investigate page opportunities even when Google Suggest has not yet "
        "formed an exact keyword. Propose focused pages for codes, tier lists, named updates, entities, "
        "beginner flow, progression, currencies, upgrades, modes, maps, bosses, quests, and other systems "
        "only when the evidence shows page-specific information. Do not collapse distinct player needs "
        "into one umbrella guide merely because their content may overlap. "
        "For roster or collection games, inspect the supplied YouTube discovery evidence for named units, "
        "characters, bosses, modes, and items. When the same named entity is supported by at least two "
        "different videos, or by one official/creator source, propose its own entity page instead of only "
        "an umbrella roster page. Return up to twenty such named entity opportunities and up to forty total "
        "opportunities when genuinely supported. Prefer more useful, separately navigable coverage over a "
        "few oversized articles, but never fill a quota. "
        "A page opportunity needs either one official/creator source or two distinct supporting URLs. "
        "Do not propose calculators or Discord/Reddit/Trello navigation pages. A negative status page is "
        "allowed only for an exact-game Codes, update, or official-link search intent when the research "
        "itself establishes that the requested feature, active result, or official destination is currently "
        "unavailable or unverified. Such a page must still give a direct answer, last-checked scope, safe "
        "next steps, and the evidence that would change the answer; never create a generic empty page. "
        "or a tier list unless the game has a genuinely rankable set. Use short ASCII topic_suffix values "
        "that can follow the normalized game name. Return only one JSON "
        "object matching the supplied schema, without Markdown fences or commentary."
    )
    input_text = json.dumps(
        {
            "task": "Build a factual context pack and evidence-backed focused-page opportunities for keyword clustering.",
            "game": topic,
            "trusted_basic_info": trusted_context or {},
            "candidate_terms_to_disambiguate": focus,
            "youtube_discovery_evidence": youtube_discovery_evidence or [],
            "output_json_schema": CONTEXT_SCHEMA,
        },
        ensure_ascii=False,
    )
    return _call_toapis_web_research(
        api_key,
        model,
        instructions,
        input_text,
        max_tokens=16000,
    )


def _compact_candidate(item: Candidate) -> dict[str, Any]:
    return {
        "keyword": item.keyword,
        "sources": sorted(item.sources),
        "score": item.score,
        "metrics": {
            "labs_search_volume": item.labs_search_volume,
            "search_intent": item.search_intent,
            "autocomplete_best_rank": item.autocomplete_best_rank,
            "autocomplete_occurrences": item.autocomplete_occurrences,
            "trends_top": item.trends_top,
            "trends_rising": item.trends_rising,
            "youtube_views": item.youtube_views,
            "youtube_occurrences": item.youtube_occurrences,
        },
        "evidence": item.evidence[:3],
        "page_type": item.page_type,
        "entity_name": item.entity_name,
        "entity_type": item.entity_type,
        "intent": item.intent,
        "confidence": item.confidence,
        "evidence_urls": item.evidence_urls[:5],
    }


def _valid_evidence_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def supplement_context_opportunities(
    topic: str,
    candidates: list[Candidate],
    game_context: dict[str, Any],
    *,
    confidence_threshold: float = OPPORTUNITY_CONFIDENCE_THRESHOLD,
) -> tuple[list[Candidate], list[dict[str, Any]]]:
    """Admit web-researched page opportunities through a deterministic gate."""
    merged = {canonical(item.keyword): item for item in candidates}
    rejected: list[dict[str, Any]] = []
    topic_key = canonical(topic)
    trusted = game_context.get("trusted_basic_info") or {}
    profile = trusted.get("game_profile") or {}
    allowed_categories = {
        str(item.get("id") or "") for item in (profile.get("categoryCandidates") or [])
    }
    for raw in game_context.get("page_opportunities") or []:
        suffix = canonical(str(raw.get("topic_suffix") or ""))
        category = canonical(str(raw.get("category") or "")).replace(" ", "-")
        confidence = float(raw.get("confidence") or 0)
        urls = list(dict.fromkeys(
            str(value).strip()
            for value in (raw.get("evidence_urls") or [])
            if _valid_evidence_url(str(value).strip())
        ))
        source_types = {canonical(str(value)) for value in (raw.get("evidence_types") or [])}
        official = bool(raw.get("official_or_creator")) or bool(source_types & {"official", "creator"})
        reason: str | None = None
        if not suffix or suffix in {"wiki", "game", "official", "guide"}:
            reason = "missing or generic topic suffix"
        elif FORBIDDEN_STANDALONE.search(suffix):
            reason = "forbidden community/navigation topic"
        elif confidence < confidence_threshold:
            reason = f"confidence {confidence:.2f} below {confidence_threshold:.2f}"
        elif not ((official and len(urls) >= 1) or len(urls) >= 2):
            reason = "needs one official/creator source or two distinct URLs"
        elif not category or category in FORBIDDEN_CATEGORIES:
            reason = f"invalid category '{category}'"
        elif allowed_categories and category not in allowed_categories:
            reason = f"category '{category}' is outside the Basic Info profile"
        if reason:
            rejected.append({"topic_suffix": suffix, "reason": reason, "evidence_urls": urls})
            continue

        keyword = f"{topic_key} {suffix}"
        candidate = Candidate(
            keyword=keyword,
            sources={"context-opportunity", *source_types},
            evidence=[str(raw.get("player_intent") or ""), *urls],
            category=category,
            page_type=str(raw.get("page_type") or page_type_for_category(category)),
            entity_name=(str(raw.get("entity_name")).strip() if raw.get("entity_name") else None),
            entity_type=(str(raw.get("entity_type")).strip() if raw.get("entity_type") else None),
            intent=str(raw.get("player_intent") or "").strip(),
            confidence=confidence,
            evidence_urls=urls,
        )
        candidate.finish()
        candidate.score = round(
            max(candidate.score, 95 + confidence * 60 + min(24, len(urls) * 8)),
            3,
        )
        key = canonical(keyword)
        if key in merged:
            merged[key].merge(candidate)
            merged[key].score = max(merged[key].score, candidate.score)
        else:
            merged[key] = candidate
    return sorted(merged.values(), key=lambda item: (-item.score, item.keyword)), rejected


def _cluster_candidate_batch(
    api_key: str,
    topic: str,
    candidates: list[Candidate],
    game_context: dict[str, Any],
    model: str = DEFAULT_CLUSTER_MODEL,
) -> LLMCall:
    messages = [
        {
            "role": "system",
            "content": (
                "You are the final editorial keyword clustering gate for an information-rich "
                "unofficial game guide site. "
                "Decide every supplied candidate exactly once. Ground semantic judgments in the supplied "
                "game context and evidence. Treat trusted_basic_info from the upstream platform identity "
                "pipeline as authoritative game-specific evidence. Never create a keyword that is not in "
                "the candidate list. Strictly drop terms about another game or an unrelated meaning of the "
                "same name. Keep same-game topics that can support a useful guide page even when search "
                "volume is sparse or some details remain provisional. Return only requested JSON."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "game": canonical(topic),
                    "game_context": game_context,
                    "policy": {
                        "target": (
                            "Build broad, useful game-guide coverage while excluding unrelated topics. "
                            "Minor uncertainty is acceptable for an unofficial information site."
                        ),
                        "maximum_keywords": 40,
                        "maximum_categories": 8,
                        "category_minimum": (
                            "Do not force a page count. Keep multiple distinct, evidence-backed entity, "
                            "codes, tier-list, and update intents when they solve different player needs; "
                            "accept fewer for a simple game and never synthesize an unsupported topic."
                        ),
                        "category_overlap": (
                            "Small overlap between categories and articles is acceptable. Do not merge "
                            "distinct useful guide intents merely because their content may overlap."
                        ),
                        "category_names": (
                            "One lowercase English slug; use 'tier-list' for rankings. "
                            "Never wiki/gameplay/general."
                        ),
                        "standalone_forbidden": [
                            "reddit", "discord", "trello", "logo", "youtube", "game link"
                        ],
                        "youtube_only": (
                            "YouTube-only evidence is allowed. Judge the candidate by search usefulness, "
                            "specificity, repeated support across videos, and consistency with the game "
                            "context. Multi-video mechanics such as movement, juking, passing, or map "
                            "positioning can support an unofficial guide even before Suggest demand appears. "
                            "Drop one-off entertainment/challenge titles and unrelated topics."
                        ),
                        "low_confidence": (
                            f"Drop when confidence is below {LOW_CONFIDENCE_THRESHOLD}. Official/trusted "
                            "basic information and clearly game-specific video evidence may justify "
                            "confidence at or above this threshold."
                        ),
                        "codes": "At most one codes keyword.",
                        "duplicates": (
                            "Merge singular/plural, wording variants, and identical intent into the best "
                            "existing candidate. The merge_into target must be an exact candidate keyword."
                        ),
                        "release_date": (
                            "If the game is released, do not mechanically delete release-date intent. "
                            "Keep only when evidence suggests durable historical/current search value; "
                            "otherwise merge into an existing updates/launch candidate or drop."
                        ),
                        "guide": (
                            "Use a guide category when at least one eligible informational candidate "
                            "supports it; never invent or force a weak keyword just to fill the category."
                        ),
                    },
                    "candidates": [_compact_candidate(item) for item in candidates],
                },
                ensure_ascii=False,
            ),
        },
    ]
    return _call_toapis_chat(
        api_key,
        model,
        messages,
        _schema("keyword_cluster_decisions", CLUSTER_SCHEMA),
        reasoning_effort="high",
        max_tokens=10000,
    )


def _load_cluster_batch_checkpoint(
    path: Path,
    topic: str,
    keywords: list[str],
    model: str,
    context_fingerprint: str,
) -> LLMCall | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("version") != CLUSTER_POLICY_VERSION
        or value.get("topic") != topic
        or value.get("keywords") != keywords
        or value.get("requested_model") != model
        or value.get("context_fingerprint") != context_fingerprint
    ):
        return None
    return LLMCall(
        model=str(value.get("model") or model),
        data=dict(value["data"]),
        usage=dict(value.get("usage") or {}),
        cost_usd=None,
        response_meta=dict(value.get("response_meta") or {}),
    )


def _write_cluster_batch_checkpoint(
    path: Path,
    topic: str,
    keywords: list[str],
    requested_model: str,
    context_fingerprint: str,
    call: LLMCall,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": CLUSTER_POLICY_VERSION,
                "topic": topic,
                "keywords": keywords,
                "requested_model": requested_model,
                "context_fingerprint": context_fingerprint,
                "model": call.model,
                "data": call.data,
                "usage": call.usage,
                "response_meta": call.response_meta,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def cluster_candidates(
    api_key: str,
    topic: str,
    candidates: list[Candidate],
    game_context: dict[str, Any],
    model: str = DEFAULT_CLUSTER_MODEL,
    batch_size: int = 60,
    checkpoint_dir: Path | None = None,
) -> LLMCall:
    """Cluster every candidate in bounded calls and checkpoint each completed batch."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    ordered = sorted(candidates, key=lambda item: canonical(item.keyword))
    context_fingerprint = hashlib.sha256(
        json.dumps(game_context, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    calls: list[LLMCall] = []
    for offset in range(0, len(ordered), batch_size):
        batch = ordered[offset : offset + batch_size]
        batch_number = offset // batch_size + 1
        keywords = [item.keyword for item in batch]
        checkpoint_path = (
            checkpoint_dir / f"cluster-batch-{batch_number:03d}.json"
            if checkpoint_dir is not None
            else None
        )
        call = (
            _load_cluster_batch_checkpoint(
                checkpoint_path, topic, keywords, model, context_fingerprint
            )
            if checkpoint_path is not None
            else None
        )
        if call is None:
            call = _cluster_candidate_batch(api_key, topic, batch, game_context, model=model)
            if checkpoint_path is not None:
                _write_cluster_batch_checkpoint(
                    checkpoint_path, topic, keywords, model, context_fingerprint, call
                )
        calls.append(call)

    decisions: list[dict[str, Any]] = []
    category_purposes: list[dict[str, Any]] = []
    notes: list[str] = []
    usage: dict[str, Any] = {}
    for index, call in enumerate(calls, start=1):
        decisions.extend(call.data.get("decisions") or [])
        category_purposes.extend(call.data.get("category_purposes") or [])
        notes.extend(f"batch {index}: {note}" for note in (call.data.get("notes") or []))
        for key, value in call.usage.items():
            if isinstance(value, (int, float)):
                usage[key] = usage.get(key, 0) + value
    unique_purposes: list[dict[str, Any]] = []
    seen_purposes: set[tuple[str, str]] = set()
    for item in category_purposes:
        marker = (str(item.get("category") or ""), str(item.get("purpose") or ""))
        if marker not in seen_purposes:
            seen_purposes.add(marker)
            unique_purposes.append(item)
    return LLMCall(
        model=model,
        data={
            "topic_name": canonical(topic),
            "decisions": decisions,
            "category_purposes": unique_purposes,
            "notes": notes,
        },
        usage=usage,
        cost_usd=None,
        response_meta={
            "model": model,
            "batched": len(calls) > 1,
            "batch_count": len(calls),
            "batch_size": batch_size,
            "batches": [call.response_meta for call in calls],
            "usage": usage,
            "cost_usd": None,
        },
    )


def _category_valid(value: str) -> bool:
    return bool(value) and value not in FORBIDDEN_CATEGORIES and " " not in value


def apply_cluster_decisions(
    topic: str,
    candidates: list[Candidate],
    decisions_data: dict[str, Any],
    maximum: int = 40,
    confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
) -> tuple[list[Candidate], list[dict[str, Any]], list[str]]:
    by_keyword = {canonical(item.keyword): item for item in candidates}
    decisions: dict[str, dict[str, Any]] = {}
    audit_errors: list[str] = []
    for raw in decisions_data.get("decisions") or []:
        key = canonical(str(raw.get("keyword") or ""))
        if key not in by_keyword:
            audit_errors.append(f"LLM returned unknown keyword: {raw.get('keyword')}")
            continue
        if key in decisions:
            audit_errors.append(f"LLM returned duplicate decision: {key}")
            continue
        decisions[key] = raw

    rejected: list[dict[str, Any]] = []
    eligible: list[Candidate] = []
    for key, candidate in by_keyword.items():
        decision = decisions.get(key)
        if decision is None:
            rejected.append({"keyword": candidate.keyword, "reason": "LLM omitted candidate"})
            audit_errors.append(f"LLM omitted candidate: {candidate.keyword}")
            continue
        action = str(decision.get("action") or "drop")
        confidence = float(decision.get("confidence") or 0)
        category = canonical(str(decision.get("category") or "")).replace(" ", "-")
        reason = str(decision.get("reason") or "LLM decision")
        hard_reason: str | None = None
        tail = canonical(candidate.keyword).removeprefix(canonical(topic)).strip()
        if FORBIDDEN_STANDALONE.search(tail):
            hard_reason = "hard filter: forbidden standalone topic"
        elif confidence < confidence_threshold:
            hard_reason = f"hard filter: confidence {confidence:.2f} below {confidence_threshold:.2f}"
        elif action != "keep":
            hard_reason = f"LLM {action}: {reason}"
        elif not _category_valid(category):
            hard_reason = f"hard filter: invalid category '{category}'"
        if hard_reason:
            rejected.append(
                {
                    "keyword": candidate.keyword,
                    "reason": hard_reason,
                    "confidence": confidence,
                    "llm_reason": reason,
                    "merge_into": decision.get("merge_into"),
                }
            )
            continue
        candidate.category = category
        candidate.page_type = page_type_for_category(category)
        eligible.append(candidate)

    ranked_categories: dict[str, float] = {}
    for item in eligible:
        ranked_categories[item.category] = ranked_categories.get(item.category, 0) + item.score
    allowed = {
        name
        for name, _ in sorted(ranked_categories.items(), key=lambda pair: (-pair[1], pair[0]))[:8]
    }
    selected: list[Candidate] = []
    codes_used = False
    for candidate in sorted(eligible, key=lambda item: (-item.score, item.keyword)):
        if candidate.category not in allowed:
            rejected.append({"keyword": candidate.keyword, "reason": "hard filter: category limit"})
            continue
        if candidate.category == "codes":
            if codes_used:
                rejected.append({"keyword": candidate.keyword, "reason": "hard filter: one codes keyword"})
                continue
            codes_used = True
        selected.append(candidate)
        if len(selected) >= maximum:
            break
    selected_keys = {item.keyword for item in selected}
    for candidate in eligible:
        if candidate.keyword not in selected_keys and not any(
            item.get("keyword") == candidate.keyword for item in rejected
        ):
            rejected.append({"keyword": candidate.keyword, "reason": "hard filter: keyword limit"})
    return selected, rejected, audit_errors
