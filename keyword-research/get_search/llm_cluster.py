from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .classifier import Candidate, canonical


TOAPIS_CHAT_URL = "https://toapis.com/v1/chat/completions"
TOAPIS_RESPONSES_URL = "https://toapis.com/v1/responses"
TOAPIS_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) get-search/1.0"
DEFAULT_CONTEXT_MODEL = "gpt-5.3-codex-official"
DEFAULT_CLUSTER_MODEL = "gpt-5.6-terra"
LOW_CONFIDENCE_THRESHOLD = 0.75

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
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
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
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"ToAPIs HTTP {exc.code}: {detail}") from exc
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
    raw = _request_toapis(
        api_key,
        TOAPIS_RESPONSES_URL,
        {
            "model": model,
            "instructions": instructions,
            "input": input_text,
            "tools": [{"type": "web_search_preview"}],
            "tool_choice": "required",
            "max_output_tokens": max_tokens,
        },
        timeout_seconds,
    )
    text, annotations, output_types = _responses_text_and_annotations(raw)
    if "web_search_call" not in output_types:
        raise RuntimeError("ToAPIs context research completed without a web_search_call")
    if not text:
        raise RuntimeError("ToAPIs Responses API returned no research text")
    data = _parse_json(text)
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
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "topic", "game_type", "release_status", "release_date", "summary",
        "entities", "terminology", "official_sources", "warnings",
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
    model: str = DEFAULT_CONTEXT_MODEL,
) -> LLMCall:
    focus = [item.keyword for item in candidates[:80]]
    instructions = (
        "You research Roblox game terminology for SEO clustering. You must use web search. "
        "Prefer Roblox game pages, creator/community sources, and reliable recent sources. "
        "Do not use competitor wikis as evidence. Never invent names, dates, mechanics, or URLs. "
        "Separate the game's real concepts from generic video-title language. Return only one JSON "
        "object matching the supplied schema, without Markdown fences or commentary."
    )
    input_text = json.dumps(
        {
            "task": "Build a compact factual context pack for keyword clustering.",
            "game": topic,
            "candidate_terms_to_disambiguate": focus,
            "output_json_schema": CONTEXT_SCHEMA,
        },
        ensure_ascii=False,
    )
    return _call_toapis_web_research(
        api_key,
        model,
        instructions,
        input_text,
        max_tokens=7000,
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
    }


def cluster_candidates(
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
                "You are the final editorial keyword clustering gate for a Roblox SEO site. "
                "Decide every supplied candidate exactly once. Ground semantic judgments in the supplied "
                "game context and evidence. Never create a keyword that is not in the candidate list. "
                "Keep only topics that can support a useful search-intent page. Return only requested JSON."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "game": canonical(topic),
                    "game_context": game_context,
                    "policy": {
                        "target": "Prefer quality; fewer than 30 final keywords is allowed.",
                        "maximum_keywords": 40,
                        "maximum_categories": 8,
                        "category_minimum": "none",
                        "category_names": (
                            "One lowercase English word, except 'tier list'. Never wiki/gameplay/general."
                        ),
                        "standalone_forbidden": [
                            "reddit", "discord", "trello", "logo", "youtube", "game link"
                        ],
                        "youtube_only": (
                            "YouTube-only evidence is allowed. Judge the candidate by search usefulness, "
                            "specificity, and consistency with the game context. Keep useful topics even "
                            "when YouTube is their only source; drop only for a concrete semantic reason."
                        ),
                        "low_confidence": (
                            f"Drop when confidence is below {LOW_CONFIDENCE_THRESHOLD}."
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
        max_tokens=16000,
    )


def _category_valid(value: str) -> bool:
    return bool(value) and value not in FORBIDDEN_CATEGORIES and (
        " " not in value or value == "tier list"
    )


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
        category = canonical(str(decision.get("category") or ""))
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
