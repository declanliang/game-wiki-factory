from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .classifier import build_keywords_json, extract_candidates, select_keywords, validate_keywords
from .client import DataForSEOClient
from .collectors import (
    collect_autocomplete,
    collect_google_suggest,
    collect_labs,
    collect_trends,
    collect_youtube,
)
from .config import Settings
from .llm_cluster import (
    CONTEXT_POLICY_VERSION,
    DEFAULT_CLUSTER_MODEL,
    DEFAULT_CONTEXT_MODEL,
    LLMCall,
    apply_cluster_decisions,
    cluster_candidates,
    research_game_context,
    supplement_context_opportunities,
)
from .manual_inputs import google_suggest_path, load_manual_inputs, merge_manual_candidates


def slugify(value: str) -> str:
    return "-".join(part for part in value.lower().replace("_", " ").split() if part.isalnum())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def youtube_discovery_evidence(raw: dict[str, Any], maximum: int = 100) -> list[dict[str, Any]]:
    """Return compact, deduplicated video evidence for context research."""
    found: dict[str, dict[str, Any]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "youtube_video" and value.get("title") and value.get("url"):
                url = str(value["url"]).split("&", 1)[0]
                record = {
                    "title": str(value["title"]).strip(),
                    "url": url,
                    "views": int(value.get("views_count") or 0),
                }
                existing = found.get(url)
                if existing is None or record["views"] > existing["views"]:
                    found[url] = record
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(raw.get("youtube") or {})
    return sorted(found.values(), key=lambda item: (-item["views"], item["title"]))[:maximum]


def load_run_metadata(
    from_run: Path,
    topic: str | None,
    settings: Settings | None,
) -> dict[str, Any]:
    """Load a finished run manifest or recover metadata for a raw-only partial run."""
    manifest_path = from_run / "manifest.json"
    if manifest_path.is_file():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    if not topic:
        raise ValueError(
            "This is a partial run with raw collection files but no manifest. "
            "Provide the original topic together with --from-run."
        )
    if settings is None:
        raise ValueError("Settings are required to resume a partial run.")
    return {
        "topic": topic,
        "location": settings.location,
        "language": settings.language,
        "google_suggest_source": "cached",
    }


def load_context_checkpoint(
    run_dir: Path,
    topic: str,
    candidate_keywords: list[str],
    model: str,
) -> LLMCall | None:
    path = run_dir / "llm" / "context-checkpoint.json"
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("version") != CONTEXT_POLICY_VERSION
        or value.get("topic") != topic
        or value.get("candidate_keywords") != candidate_keywords
        or value.get("requested_model") != model
    ):
        return None
    return LLMCall(
        model=str(value.get("model") or model),
        data=dict(value["data"]),
        usage=dict(value.get("usage") or {}),
        cost_usd=None,
        response_meta=dict(value.get("response_meta") or {}),
    )


def write_context_checkpoint(
    run_dir: Path,
    topic: str,
    candidate_keywords: list[str],
    requested_model: str,
    call: LLMCall,
) -> None:
    write_json(
        run_dir / "llm" / "context-checkpoint.json",
        {
            "version": CONTEXT_POLICY_VERSION,
            "topic": topic,
            "candidate_keywords": candidate_keywords,
            "requested_model": requested_model,
            "model": call.model,
            "data": call.data,
            "usage": call.usage,
            "response_meta": call.response_meta,
        },
    )


def safe_collect(name: str, collector: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return collector()
    except Exception as exc:
        return {"source": name, "cost": 0.0, "error": str(exc), "response": None}


def collect_all(
    topic: str,
    settings: Settings,
    include_az: bool = True,
    suggest_source: str = "google",
) -> dict[str, Any]:
    client = DataForSEOClient(settings.api_login, settings.api_password, settings.timeout_seconds)
    # Keep top-level sources sequential so high-level failures and cost are easy to audit.
    return {
        "labs": safe_collect("labs", lambda: collect_labs(client, topic, settings)),
        "trends": safe_collect("trends", lambda: collect_trends(client, topic, settings)),
        "autocomplete": (
            safe_collect(
                "autocomplete", lambda: collect_autocomplete(client, topic, settings, include_az)
            )
            if suggest_source == "dataforseo"
            else safe_collect(
                "autocomplete", lambda: collect_google_suggest(topic, settings, include_az)
            )
            if suggest_source == "google"
            else {
                "source": "manual",
                "cost": 0.0,
                "queries": [],
                "skipped_reason": "manual Google Suggest input is present",
            }
        ),
        "youtube": safe_collect("youtube", lambda: collect_youtube(client, topic, settings)),
    }


def refresh_sources(
    raw: dict[str, Any],
    topic: str,
    settings: Settings,
    names: set[str],
    include_az: bool,
    suggest_source: str = "google",
) -> dict[str, Any]:
    client = DataForSEOClient(settings.api_login, settings.api_password, settings.timeout_seconds)
    collectors: dict[str, Callable[[], dict[str, Any]]] = {
        "labs": lambda: collect_labs(client, topic, settings),
        "trends": lambda: collect_trends(client, topic, settings),
        "autocomplete": lambda: (
            collect_autocomplete(client, topic, settings, include_az)
            if suggest_source == "dataforseo"
            else collect_google_suggest(topic, settings, include_az)
            if suggest_source == "google"
            else {
                "source": "manual",
                "cost": 0.0,
                "queries": [],
                "skipped_reason": "manual Google Suggest input is present",
            }
        ),
        "youtube": lambda: collect_youtube(client, topic, settings),
    }
    for name in names:
        raw[name] = safe_collect(name, collectors[name])
    return raw


def count_source_items(raw: dict[str, Any]) -> dict[str, int]:
    from .client import first_task_results

    labs_count = 0
    for result in first_task_results(raw.get("labs", {}).get("response") or {}):
        labs_count += len(result.get("items") or [])
    trends_count = 0
    for result in first_task_results(raw.get("trends", {}).get("response") or {}):
        for item in result.get("items") or []:
            if item.get("type") == "google_trends_queries_list":
                data = item.get("data") or {}
                trends_count += len(data.get("top") or []) + len(data.get("rising") or [])
    autocomplete_count = 0
    autocomplete_errors = 0
    autocomplete_empty = 0
    for query in raw.get("autocomplete", {}).get("queries") or []:
        if query.get("error"):
            if "40102" in str(query.get("error")) and "No Search Results" in str(query.get("error")):
                autocomplete_empty += 1
            else:
                autocomplete_errors += 1
        elif query.get("empty_reason"):
            autocomplete_empty += 1
        elif "suggestions" in query and not query.get("suggestions"):
            autocomplete_empty += 1
        autocomplete_count += len(query.get("suggestions") or [])
        for result in first_task_results(query.get("response") or {}):
            autocomplete_count += len(result.get("items") or [])
    youtube_count = 0
    for result in first_task_results(raw.get("youtube", {}).get("response") or {}):
        youtube_count += sum(1 for item in result.get("items") or [] if item.get("type") == "youtube_video")
    return {
        "labs": labs_count,
        "trends_queries": trends_count,
        "autocomplete_suggestions": autocomplete_count,
        "autocomplete_errors": autocomplete_errors,
        "autocomplete_empty_queries": autocomplete_empty,
        "youtube_videos": youtube_count,
    }


def total_cost(raw: dict[str, Any]) -> float:
    return round(sum(float(value.get("cost") or 0) for value in raw.values()), 6)


def write_report(
    run_dir: Path,
    topic: str,
    manifest: dict[str, Any],
    candidates: list[Any],
    selected: list[Any],
    rejected: list[dict[str, str]],
    errors: list[str],
) -> None:
    category_counts: dict[str, int] = {}
    for item in selected:
        category_counts[item.category] = category_counts.get(item.category, 0) + 1
    lines = [
        f"# Keyword research report: {topic}",
        "",
        f"- Generated: `{manifest['generated_at']}`",
        f"- Location/language: `{manifest['location']}` / `{manifest['language']}`",
        f"- Actual DataForSEO cost: `${manifest['total_cost_usd']:.6f}`",
        f"- Google Suggest source: `{manifest.get('google_suggest_source', 'dataforseo')}`",
        (
            "- Manual input: "
            f"`{manifest.get('manual_input', {}).get('accepted_keywords', 0)}` accepted / "
            f"`{manifest.get('manual_input', {}).get('rejected_keywords', 0)}` rejected"
        ),
        (
            "- ToAPIs usage: "
            f"`{manifest.get('toapis', {}).get('total_tokens', 0)}` tokens "
            "(USD cost is not returned by the API)"
        ),
        f"- Clustering mode: `{manifest.get('cluster_mode', 'rules')}`",
        f"- Candidates after normalization: `{len(candidates)}`",
        f"- Selected keywords: `{len(selected)}`",
        f"- Validation: `{'PASS' if not errors else 'FAIL'}`",
        "",
        "## Source results",
        "",
    ]
    for key, value in manifest["source_counts"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Categories", ""])
    for category, count in category_counts.items():
        lines.append(f"- {category}: `{count}`")
    if errors:
        lines.extend(["", "## Validation errors", ""])
        lines.extend(f"- {error}" for error in errors)
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Labs search volume is DataForSEO/Google monthly volume, not Similarweb 28-day volume.",
            "- Google Trends values are relative popularity, not absolute search counts.",
            "- YouTube titles are converted into candidate topics using explicit phrase rules and multi-video gates.",
            "- Web-researched page opportunities require one official/creator source or two distinct URLs.",
            "- Reddit, Discord, Trello, logo, YouTube and game-link topics are hard-filtered.",
            f"- Rejected records: `{len(rejected)}`. See `candidates.json` and `llm/rejected.json`.",
        ]
    )
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_pipeline(
    root: Path,
    topic: str | None,
    settings: Settings | None,
    include_az: bool = True,
    from_run: Path | None = None,
    refresh: set[str] | None = None,
    cluster_mode: str = "llm",
    context_model: str = DEFAULT_CONTEXT_MODEL,
    cluster_model: str = DEFAULT_CLUSTER_MODEL,
    trusted_context: dict[str, Any] | None = None,
    output_run_dir: Path | None = None,
) -> Path:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if from_run:
        existing_manifest = load_run_metadata(from_run, topic, settings)
        topic = str(existing_manifest["topic"])
        manual_input_dir = root / "input" / slugify(topic)
        manual_suggest = google_suggest_path(manual_input_dir)
        requested_suggest_source = settings.suggest_source if settings else "auto"
        if (
            "autocomplete" in (refresh or set())
            and requested_suggest_source == "manual"
            and manual_suggest is None
        ):
            raise ValueError(f"Missing manual Google Suggest file in {manual_input_dir}")
        resolved_suggest_source = (
            "manual"
            if requested_suggest_source == "manual"
            else "dataforseo"
            if requested_suggest_source == "dataforseo"
            else "google"
        )
        suggest_source = str(existing_manifest.get("google_suggest_source") or "cached")
        if "autocomplete" in (refresh or set()):
            suggest_source = resolved_suggest_source
        raw = {
            name: json.loads((from_run / "raw" / f"{name}.json").read_text(encoding="utf-8"))
            for name in ("labs", "trends", "autocomplete", "youtube")
        }
        if refresh:
            if settings is None:
                raise ValueError("settings are required when refreshing a source")
            raw = refresh_sources(
                raw, topic, settings, refresh, include_az, resolved_suggest_source
            )
            for name in refresh:
                write_json(from_run / "raw" / f"{name}.json", raw[name])
        run_dir = from_run
        location = existing_manifest["location"]
        language = existing_manifest["language"]
    else:
        if not topic or settings is None:
            raise ValueError("topic and settings are required for a new collection")
        manual_input_dir = root / "input" / slugify(topic)
        manual_suggest = google_suggest_path(manual_input_dir)
        if settings.suggest_source == "manual" and manual_suggest is None:
            raise ValueError(f"Missing manual Google Suggest file in {manual_input_dir}")
        suggest_source = (
            "manual"
            if settings.suggest_source == "manual"
            else "dataforseo"
            if settings.suggest_source == "dataforseo"
            else "google"
        )
        raw = collect_all(topic, settings, include_az, suggest_source)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = output_run_dir or root / "output" / f"{slugify(topic)}-{timestamp}"
        if run_dir.exists() and any(run_dir.iterdir()):
            raise ValueError(
                f"Output run directory is not empty: {run_dir}. "
                "Use --from-run to resume it."
            )
        run_dir.mkdir(parents=True, exist_ok=True)
        location = settings.location
        language = settings.language
        for name, value in raw.items():
            write_json(run_dir / "raw" / f"{name}.json", value)

    candidates, rejected = extract_candidates(topic, raw)
    manual_candidates, manual_rejected, manual_summary = load_manual_inputs(
        topic, manual_input_dir
    )
    manual_summary["directory"] = str(manual_input_dir.relative_to(root))
    candidates = merge_manual_candidates(topic, candidates, manual_candidates)
    rejected.extend(manual_rejected)
    rules_selected = select_keywords(candidates, maximum=40)
    rules_keywords = build_keywords_json(topic, rules_selected)
    llm_rejected: list[dict[str, Any]] = []
    opportunity_rejected: list[dict[str, Any]] = []
    llm_audit_errors: list[str] = []
    llm_manifest: dict[str, Any] = {}
    if cluster_mode == "llm":
        if settings is None or not settings.toapis_api_key:
            raise ValueError(
                "ToAPIs key is required for LLM clustering. Configure TOAPIS_KEY "
                "or TOAPIS_API_KEY, or use --cluster-mode rules."
            )
        candidate_keywords = [item.keyword for item in candidates]
        video_evidence = youtube_discovery_evidence(raw)
        video_fingerprint = hashlib.sha256(
            json.dumps(video_evidence, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        context_checkpoint_inputs = [*candidate_keywords, f"youtube-evidence:{video_fingerprint}"]
        context_call = load_context_checkpoint(
            run_dir, topic, context_checkpoint_inputs, context_model
        )
        if context_call is None:
            context_call = research_game_context(
                settings.toapis_api_key,
                topic,
                candidates,
                trusted_context=trusted_context,
                youtube_discovery_evidence=video_evidence,
                model=context_model,
            )
            write_context_checkpoint(
                run_dir, topic, context_checkpoint_inputs, context_model, context_call
            )
        effective_context = dict(context_call.data)
        if trusted_context:
            effective_context["trusted_basic_info"] = trusted_context
        candidates, opportunity_rejected = supplement_context_opportunities(
            topic, candidates, effective_context
        )
        cluster_call = cluster_candidates(
            settings.toapis_api_key,
            topic,
            candidates,
            effective_context,
            model=cluster_model,
            checkpoint_dir=run_dir / "llm",
        )
        selected, llm_rejected, llm_audit_errors = apply_cluster_decisions(
            topic, candidates, cluster_call.data, maximum=40
        )
        keywords = build_keywords_json(topic, selected)
        context_tokens = int(context_call.usage.get("total_tokens") or 0)
        cluster_tokens = int(cluster_call.usage.get("total_tokens") or 0)
        llm_manifest = {
            "context_model": context_call.response_meta.get("model") or context_model,
            "cluster_model": cluster_call.response_meta.get("model") or cluster_model,
            "context_usage": context_call.usage,
            "cluster_usage": cluster_call.usage,
            "total_tokens": context_tokens + cluster_tokens,
            "cost_usd": None,
        }
        write_json(run_dir / "llm" / "game-context.json", effective_context)
        write_json(run_dir / "llm" / "context-response.json", context_call.response_meta)
        write_json(run_dir / "llm" / "cluster-decisions.json", cluster_call.data)
        write_json(run_dir / "llm" / "cluster-response.json", cluster_call.response_meta)
        write_json(
            run_dir / "llm" / "rejected.json",
            {
                "rejected": llm_rejected,
                "opportunity_rejected": opportunity_rejected,
                "audit_errors": llm_audit_errors,
            },
        )
    else:
        selected = rules_selected
        keywords = rules_keywords
    errors = validate_keywords(keywords)
    errors.extend(llm_audit_errors)
    source_counts = count_source_items(raw)
    source_counts["manual_similarweb_keywords"] = sum(
        int(item["accepted_keywords"])
        for item in manual_summary["files"]
        if item["source"] == "similarweb"
    )
    source_counts["manual_google_suggest_keywords"] = sum(
        int(item["accepted_keywords"])
        for item in manual_summary["files"]
        if item["source"] == "google_suggest_manual"
    )
    source_counts["manual_google_trends_keywords"] = sum(
        int(item["accepted_keywords"])
        for item in manual_summary["files"]
        if str(item["source"]).startswith("google_trends_manual_")
    )
    manifest = {
        "topic": topic,
        "generated_at": generated_at,
        "location": location,
        "language": language,
        "autocomplete_mode": "main+a-z" if include_az else "main-only",
        "google_suggest_source": suggest_source,
        "source_counts": source_counts,
        "source_costs_usd": {name: float(value.get("cost") or 0) for name, value in raw.items()},
        "manual_input": manual_summary,
        "total_cost_usd": total_cost(raw),
        "cluster_mode": cluster_mode,
        "toapis": llm_manifest,
        "context_opportunities": {
            "admitted": sum("context-opportunity" in item.sources for item in candidates),
            "rejected": len(opportunity_rejected),
        },
        "validation_errors": errors,
    }
    write_json(run_dir / "manifest.json", manifest)
    write_json(
        run_dir / "candidates.json",
        {"topic": topic, "candidates": [item.as_dict() for item in candidates], "rejected": rejected},
    )
    write_json(
        run_dir / "manual-input.json",
        {"summary": manual_summary, "rejected": manual_rejected},
    )
    write_json(run_dir / "keywords-rules.json", rules_keywords)
    write_json(run_dir / "keywords.json", keywords)
    write_report(
        run_dir, topic, manifest, candidates, selected,
        rejected + opportunity_rejected + llm_rejected, errors
    )
    if errors:
        raise ValueError("Output validation failed: " + "; ".join(errors))
    return run_dir
