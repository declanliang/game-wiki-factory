from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .config import Settings
from .http import CachedHttpClient
from .util import cache_key, clean_json_text, dump_json, load_json, utc_now


TOAPIS_RESPONSES_URL = "https://toapis.com/v1/responses"


class LlmError(RuntimeError):
    pass


class LlmClient:
    def __init__(self, settings: Settings, http: CachedHttpClient):
        self.settings = settings
        self.http = http
        self.cache_dir = settings.cache_dir / "llm"
        self.calls: list[dict[str, Any]] = []

    def generate(self, task: str, system: str, prompt: str, schema: dict[str, Any], *, web: bool, ttl: int) -> tuple[dict[str, Any], dict[str, Any]]:
        model = self.settings.toapis_web_model if web else self.settings.toapis_model
        key = cache_key("toapis-responses-v1", task, model, system, prompt, schema, web)
        cached = self.cache_dir / f"{key}.json"
        if not self.settings.refresh and cached.exists() and time.time() - cached.stat().st_mtime < ttl:
            record = load_json(cached)
            meta = {**record["meta"], "cached": True}
            self.calls.append(meta)
            return record["data"], meta

        errors: list[str] = []
        if self.settings.toapis_api_key:
            try:
                data, meta = self._toapis(task, system, prompt, schema, web)
                dump_json(cached, {"data": data, "meta": meta})
                self.calls.append(meta)
                return data, meta
            except Exception as exc:
                errors.append(f"ToAPIs: {exc}")
        if web and self.settings.perplexity_api_key:
            try:
                data, meta = self._perplexity(task, system, prompt, schema)
                if errors:
                    meta["fallbackFrom"] = list(errors)
                dump_json(cached, {"data": data, "meta": meta})
                self.calls.append(meta)
                return data, meta
            except Exception as exc:
                errors.append(f"Perplexity: {exc}")
        if not self.settings.toapis_api_key and not (web and self.settings.perplexity_api_key):
            errors.append("no usable API key configured")
        raise LlmError(f"{task} failed; " + " | ".join(errors))

    def _toapis(self, task: str, system: str, prompt: str, schema: dict[str, Any], web: bool) -> tuple[dict[str, Any], dict[str, Any]]:
        model = self.settings.toapis_web_model if web else self.settings.toapis_model
        payload: dict[str, Any] = {
            "model": model,
            "instructions": system,
            "input": _schema_bound_prompt(prompt, schema),
            "max_output_tokens": 10000,
            "reasoning": {"effort": self.settings.toapis_reasoning_effort},
        }
        if web:
            payload["tools"] = [{"type": "web_search_preview"}]
            payload["tool_choice"] = "required"

        started = time.monotonic()
        response = self._post_toapis(payload)
        content = _responses_text(response)
        retry_response: dict[str, Any] | None = None
        try:
            data = clean_json_text(content)
        except (ValueError, json.JSONDecodeError):
            retry_payload = copy.deepcopy(payload)
            retry_payload["input"] = _schema_bound_prompt(
                prompt + "\n\nYour previous answer was malformed or truncated. Repeat the task and return one complete JSON object only.",
                schema,
            )
            retry_response = self._post_toapis(retry_payload)
            content = _responses_text(retry_response)
            data = clean_json_text(content)

        repair_response: dict[str, Any] | None = None
        try:
            self._validate(task, data, schema)
        except LlmError as initial_error:
            data, repair_response = self._repair_toapis(task, content, schema, str(initial_error))

        elapsed = round(time.monotonic() - started, 2)
        usage = response.get("usage") or {}
        retry_usage = (retry_response or {}).get("usage") or {}
        repair_usage = (repair_response or {}).get("usage") or {}
        all_responses = [item for item in [response, retry_response, repair_response] if item]
        meta = {
            "task": task,
            "provider": "toapis",
            "model": response.get("model", model),
            "requestedModel": model,
            "elapsedSeconds": elapsed,
            "costUsd": _sum_optional(_usage_cost(usage), _usage_cost(retry_usage), _usage_cost(repair_usage)),
            "promptTokens": _sum_optional(usage.get("input_tokens"), retry_usage.get("input_tokens"), repair_usage.get("input_tokens")),
            "completionTokens": _sum_optional(usage.get("output_tokens"), retry_usage.get("output_tokens"), repair_usage.get("output_tokens")),
            "webSearchCalls": sum(_web_search_calls(item) for item in all_responses),
            "cached": False,
            "completedAt": utc_now(),
            "responseId": response.get("id"),
            "schemaRepaired": repair_response is not None,
            "retriedMalformed": retry_response is not None,
        }
        return data, meta

    def _post_toapis(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.http.post_json(
            TOAPIS_RESPONSES_URL,
            payload,
            {"Authorization": f"Bearer {self.settings.toapis_api_key}", "Content-Type": "application/json"},
            timeout=self.settings.request_timeout,
        )
        status = response.get("status")
        if status != "completed":
            detail = response.get("error") or response.get("incomplete_details") or "no error details"
            raise LlmError(f"Responses API status={status!r}: {detail}")
        return response

    def _repair_toapis(self, task: str, invalid_content: str, schema: dict[str, Any], error: str) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = {
            "model": self.settings.toapis_model,
            "instructions": "You are a lossless JSON schema transformer. Return only corrected JSON. Never add facts, URLs, numbers, codes, or claims.",
            "input": (
                f"Transform SOURCE_JSON to match TARGET_SCHEMA exactly. Validation errors: {error}\n\n"
                f"TARGET_SCHEMA:\n{json.dumps(schema, ensure_ascii=False)}\n\nSOURCE_JSON:\n{invalid_content}"
            ),
            "max_output_tokens": 10000,
            "reasoning": {"effort": "low"},
        }
        response = self._post_toapis(payload)
        data = clean_json_text(_responses_text(response))
        try:
            self._validate(task + " repair", data, schema)
        except LlmError:
            # Models occasionally preserve every requested fact but miss a
            # localized maxLength by a few characters even after repair.
            # Deterministically compact only over-limit strings; all other
            # schema errors still fail the validation below.
            data = _compact_schema_strings(data, schema)
            self._validate(task + " repair", data, schema)
        return data, response

    def _perplexity(self, task: str, system: str, prompt: str, schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = {
            "model": self.settings.perplexity_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "max_tokens": 10000,
            "temperature": 0.15,
            "response_format": {"type": "json_schema", "json_schema": {"schema": _provider_schema(schema)}},
            "web_search_options": {"search_context_size": "medium"},
        }
        started = time.monotonic()
        response = self.http.post_json(
            "https://api.perplexity.ai/v1/sonar", payload,
            {"Authorization": f"Bearer {self.settings.perplexity_api_key}", "Content-Type": "application/json"},
            timeout=self.settings.request_timeout,
        )
        elapsed = round(time.monotonic() - started, 2)
        choices = response.get("choices") or []
        if not choices:
            raise LlmError("empty choices")
        data = clean_json_text(choices[0]["message"]["content"])
        self._validate(task, data, schema)
        usage = response.get("usage") or {}
        cost = usage.get("cost") or {}
        meta = {
            "task": task, "provider": "perplexity", "model": response.get("model", self.settings.perplexity_model),
            "elapsedSeconds": elapsed, "costUsd": cost.get("total_cost") if isinstance(cost, dict) else None,
            "promptTokens": usage.get("prompt_tokens"), "completionTokens": usage.get("completion_tokens"),
            "webSearchCalls": None, "cached": False, "completedAt": utc_now(), "responseId": response.get("id"),
        }
        return data, meta

    @staticmethod
    def _validate(task: str, data: Any, schema: dict[str, Any]) -> None:
        errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda issue: [str(part) for part in issue.path])
        if errors:
            rendered = "; ".join(f"{'.'.join(map(str, issue.path)) or '$'}: {issue.message}" for issue in errors[:8])
            raise LlmError(f"{task} returned invalid JSON: {rendered}")


def _schema_bound_prompt(prompt: str, schema: dict[str, Any]) -> str:
    return (
        f"{prompt}\n\nOUTPUT CONTRACT:\nReturn exactly one JSON object, without Markdown fences or commentary, "
        "matching this JSON Schema. Key spelling and capitalization are exact.\n"
        f"{json.dumps(schema, ensure_ascii=False, separators=(',', ':'))}"
    )


def _responses_text(response: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in response.get("output") or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    if not chunks:
        output_types = [item.get("type") for item in response.get("output") or []]
        raise LlmError(f"Responses API returned no output_text; output types={output_types}")
    return "\n".join(chunks)


def _web_search_calls(response: dict[str, Any]) -> int:
    return sum(item.get("type") == "web_search_call" for item in response.get("output") or [])


def _usage_cost(usage: dict[str, Any]) -> float | int | None:
    cost = usage.get("cost") or usage.get("total_cost")
    if isinstance(cost, dict):
        return cost.get("total_cost") or cost.get("total")
    return cost if isinstance(cost, (int, float)) else None


def _sum_optional(*values: Any) -> float | int | None:
    numeric = [value for value in values if isinstance(value, (int, float))]
    return sum(numeric) if numeric else None


def _compact_schema_strings(value: Any, schema: dict[str, Any], root: dict[str, Any] | None = None) -> Any:
    """Compact only strings exceeding JSON Schema maxLength constraints."""
    root = root or schema
    if "$ref" in schema:
        ref = str(schema["$ref"])
        if ref.startswith("#/"):
            resolved: Any = root
            for part in ref[2:].split("/"):
                resolved = resolved[part.replace("~1", "/").replace("~0", "~")]
            schema = resolved
    if isinstance(value, str):
        limit = schema.get("maxLength")
        if not isinstance(limit, int) or len(value) <= limit:
            return value
        if limit <= 1:
            return value[:limit]
        prefix = value[: limit - 1].rstrip(" ,.;:!?、。，：；！？-–—&")
        if " " in prefix and len(prefix) >= max(20, int(limit * 0.7)):
            prefix = prefix.rsplit(" ", 1)[0].rstrip(" ,.;:!?-–—&")
        return prefix[: limit - 1] + "…"
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        return {
            key: _compact_schema_strings(child, properties.get(key, {}), root)
            for key, child in value.items()
        }
    if isinstance(value, list):
        item_schema = schema.get("items") or {}
        return [_compact_schema_strings(child, item_schema, root) for child in value]
    return value


def _provider_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove keywords unsupported by some OpenAI-compatible structured-output gateways."""
    result = copy.deepcopy(schema)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            value.pop("format", None)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(result)
    return result
