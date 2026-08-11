"""Incremental English content publishing for existing game wiki sites.

This is the executable side of the Growth agent contract.  A separate Growth
agent may decide, from GSC/search data, that an already-published site should
receive one or more new English articles.  This module keeps that power narrow:

* only existing workspaces may be modified;
* only English article creation is supported in this first version;
* proposals must target categories already present in ``intake/site-plan.json``;
* final GitHub push and Workers Static Assets deploy still go through the
  Factory publisher.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orchestrate_wiki import (
    PipelineError,
    ROOT,
    build_subprocess_env,
    read_json,
    reconcile_homepage_guide_links,
    run_command,
    slugify,
    sync_template_source,
    validate_articles,
    write_json,
)


MAX_PROPOSALS_PER_RUN = 5
SUPPORTED_ACTIONS = {"create_article"}


def keyword_to_slug(keyword: str) -> str:
    """Mirror SEO Scout's article filename slug for duplicate checks."""
    return re.sub(r"[^a-z0-9-]", "", keyword.lower().replace(" ", "-"))


def _now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _collapse(value: object) -> str:
    return " ".join(str(value or "").split())


def normalize_growth_config(config: dict[str, Any]) -> dict[str, Any]:
    task_type = str(config.get("taskType") or "").strip()
    if task_type != "siteGrowthContent":
        raise ValueError("growth config taskType must be siteGrowthContent")
    allowed = {
        "schemaVersion",
        "taskType",
        "slug",
        "game",
        "siteUrl",
        "githubRepo",
        "source",
        "publish",
        "proposals",
    }
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise ValueError(f"unknown growth config field(s): {', '.join(unknown)}")

    slug_source = _collapse(config.get("slug") or config.get("game"))
    if not slug_source:
        raise ValueError("growth config requires slug or game")
    normalized_slug = slugify(slug_source)
    proposals = config.get("proposals")
    if not isinstance(proposals, list) or not proposals:
        raise ValueError("growth config proposals must be a non-empty array")
    if len(proposals) > MAX_PROPOSALS_PER_RUN:
        raise ValueError(f"growth config supports at most {MAX_PROPOSALS_PER_RUN} proposals per run")

    normalized_proposals: list[dict[str, Any]] = []
    seen_keywords: set[str] = set()
    for index, proposal in enumerate(proposals):
        if not isinstance(proposal, dict):
            raise ValueError(f"proposals[{index}] must be an object")
        action = str(proposal.get("action") or "create_article").strip()
        if action not in SUPPORTED_ACTIONS:
            raise ValueError(
                f"proposals[{index}].action must be create_article; "
                "Spanish or rewrite actions belong to a later Growth phase"
            )
        keyword = _collapse(proposal.get("keyword") or proposal.get("primaryKeyword"))
        if not keyword:
            raise ValueError(f"proposals[{index}].keyword must be a non-empty string")
        keyword_key = keyword.casefold()
        if keyword_key in seen_keywords:
            raise ValueError(f"duplicate growth keyword: {keyword}")
        seen_keywords.add(keyword_key)
        category = slugify(_collapse(proposal.get("targetCategory") or proposal.get("category")))
        normalized_proposals.append(
            {
                "action": action,
                "keyword": keyword,
                "targetCategory": category,
                "intent": _collapse(proposal.get("intent")),
                "reason": _collapse(proposal.get("reason")),
                "evidence": proposal.get("evidence") if isinstance(proposal.get("evidence"), dict) else {},
            }
        )

    return {
        "schemaVersion": 1,
        "taskType": "siteGrowthContent",
        "slug": normalized_slug,
        "game": _collapse(config.get("game")),
        "siteUrl": _collapse(config.get("siteUrl")),
        "githubRepo": _collapse(config.get("githubRepo")),
        "source": _collapse(config.get("source")) or "growth-agent",
        "publish": bool(config.get("publish", True)),
        "proposals": normalized_proposals,
    }


def _published_category_map(site_plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for category in site_plan.get("categories") or []:
        category_id = str(category.get("id") or "").strip()
        if category_id and category.get("status") == "published":
            result[category_id] = category
    return result


def _existing_article_slugs(project_dir: Path) -> set[str]:
    slugs: set[str] = set()
    for base in (project_dir / "content" / "en", project_dir / "intake" / "articles" / "en"):
        if not base.is_dir():
            continue
        for path in base.rglob("*.mdx"):
            slugs.add(path.stem)
    return slugs


def select_new_proposals(
    config: dict[str, Any],
    site_plan: dict[str, Any],
    project_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    categories = _published_category_map(site_plan)
    existing_slugs = _existing_article_slugs(project_dir)
    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for proposal in config["proposals"]:
        category = proposal["targetCategory"]
        keyword = proposal["keyword"]
        slug = keyword_to_slug(keyword)
        if category not in categories:
            skipped.append({"keyword": keyword, "reason": f"category-not-published:{category}"})
            continue
        if slug in existing_slugs:
            skipped.append({"keyword": keyword, "reason": f"article-exists:{slug}"})
            continue
        accepted.append({**proposal, "slug": slug})
    return accepted, skipped


def build_growth_seo_keywords(
    site_plan: dict[str, Any],
    proposals: list[dict[str, Any]],
) -> dict[str, Any]:
    game = site_plan.get("game") or {}
    game_name = str(game.get("name") or "").strip()
    platform = str(game.get("platform") or "Game").strip()
    categories = _published_category_map(site_plan)
    topic_specs: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[str]] = {}
    for proposal in proposals:
        keyword = proposal["keyword"]
        category_id = proposal["targetCategory"]
        category = categories[category_id]
        intent = proposal.get("intent") or f"Answer the player search intent behind {keyword}."
        evidence = proposal.get("evidence") or {}
        topic_specs[keyword] = {
            "primaryKeyword": keyword,
            "researchQuery": (
                keyword
                if platform.casefold() in keyword.casefold().split()
                else f"{platform} {keyword}"
            ),
            "pageType": "guide",
            "intent": intent,
            "userQuestion": intent,
            "mustAnswer": [intent],
            "distinctValue": (
                proposal.get("reason")
                or f"Create a focused page that satisfies {keyword} without duplicating existing guides."
            ),
            "allowedSharedContext": [
                "brief game identity",
                "relevant prerequisites",
                "closely related mechanics",
            ],
            "overlapPolicy": (
                "Limited shared background is allowed. The page must provide a distinct answer "
                "for this keyword and should link conceptually to nearby guides instead of copying them."
            ),
            "demandClass": "gsc-backed" if evidence else "growth-backed",
            "confidence": evidence.get("confidence") or proposal.get("priority"),
            "discoverySources": ["growth-agent"],
            "evidenceUrls": list(evidence.get("urls") or []),
        }
        grouped.setdefault(category_id, []).append(keyword)
    return {
        "game_name": game_name,
        "filter_keyword": f"{platform} {game_name}",
        "languages": [],
        "trusted_context": {
            "game": game,
            "category_descriptions": {
                category_id: category.get("description", "")
                for category_id, category in categories.items()
            },
            "policy": "Use as trusted same-game context; search results are discovery evidence, not verified numeric facts.",
        },
        "topic_specs": topic_specs,
        "categories": [
            {
                "category": category_id,
                "keywords": keywords,
                "topics": [
                    {"keyword": keyword, **topic_specs[keyword]}
                    for keyword in keywords
                ],
            }
            for category_id, keywords in grouped.items()
        ],
    }


def merge_growth_articles(
    generated_articles: Path,
    intake_articles: Path,
    content_articles: Path,
    proposals: list[dict[str, Any]],
) -> list[dict[str, str]]:
    added: list[dict[str, str]] = []
    for proposal in proposals:
        category = proposal["targetCategory"]
        slug = proposal["slug"]
        source = generated_articles / "en" / category / f"{slug}.mdx"
        if not source.is_file():
            raise PipelineError(f"Growth article was not generated or did not pass QA: en/{category}/{slug}.mdx")
        for base in (intake_articles / "en" / category, content_articles / "en" / category):
            base.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, base / source.name)
        added.append(
            {
                "keyword": proposal["keyword"],
                "category": category,
                "path": f"en/{category}/{slug}.mdx",
            }
        )
    return added


def update_site_plan_with_growth(
    site_plan: dict[str, Any],
    proposals: list[dict[str, Any]],
) -> dict[str, Any]:
    result = json.loads(json.dumps(site_plan, ensure_ascii=False))
    by_id = {
        str(category.get("id") or ""): category
        for category in result.get("categories") or []
    }
    for proposal in proposals:
        category = by_id[proposal["targetCategory"]]
        keyword = proposal["keyword"]
        keywords = category.setdefault("keywords", [])
        if keyword not in keywords:
            keywords.append(keyword)
        topics = category.setdefault("topics", [])
        if keyword not in {str(item.get("keyword") or "") for item in topics if isinstance(item, dict)}:
            topics.append(
                {
                    "keyword": keyword,
                    "primaryKeyword": keyword,
                    "pageType": "guide",
                    "intent": proposal.get("intent"),
                    "demandClass": "growth-backed",
                    "discoverySources": ["growth-agent"],
                }
            )
        category["articleCount"] = int(category.get("articleCount") or 0) + 1
        sources = category.setdefault("sources", [])
        if "growth-agent" not in sources:
            sources.append("growth-agent")
    result["growthUpdatedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return result


def run_growth_content(config: dict[str, Any], *, result_path: Path | None = None) -> dict[str, Any]:
    normalized = normalize_growth_config(config)
    projects_root = Path(os.environ.get("GAMEWIKI_PROJECTS_ROOT", ROOT.parent)).expanduser().resolve()
    project_dir = (projects_root / normalized["slug"]).resolve()
    if project_dir.parent != projects_root:
        raise PipelineError("refusing to operate outside GAMEWIKI_PROJECTS_ROOT")
    if not (project_dir / "intake" / "site-plan.json").is_file():
        raise PipelineError(f"Growth target is not an existing Factory site workspace: {project_dir}")

    run_id = _now_compact()
    state_dir = project_dir / ".gamewiki" / "growth" / run_id
    logs_dir = state_dir / "logs"
    run_log_path = logs_dir / "growth-run.log"
    site_plan_path = project_dir / "intake" / "site-plan.json"
    site_plan = read_json(site_plan_path)
    active, skipped = select_new_proposals(normalized, site_plan, project_dir)
    write_json(state_dir / "input.json", normalized)
    write_json(state_dir / "proposal-selection.json", {"accepted": active, "skipped": skipped})
    if not active:
        raise PipelineError(f"No usable growth proposals after validation: {skipped}")

    seo_keywords = build_growth_seo_keywords(site_plan, active)
    keywords_path = state_dir / "growth-seo-keywords.json"
    write_json(keywords_path, seo_keywords)

    env = build_subprocess_env(ROOT)
    seo_dir = ROOT / "pipeline" / "seo-scout"
    content_project_dir = project_dir / ".gamewiki" / "content-pipeline"
    if not (seo_dir / "seoscout").is_dir():
        raise PipelineError(f"seo-scout source is missing: {seo_dir}")
    run_command(
        [
            sys.executable,
            "-m",
            "seoscout",
            "--project-dir",
            str(content_project_dir),
            "run",
            "--keywords",
            str(keywords_path),
        ],
        cwd=seo_dir,
        env=env,
        log_path=logs_dir / "seo-scout-growth.log",
        run_log_path=run_log_path,
    )

    added = merge_growth_articles(
        content_project_dir / "articles",
        project_dir / "intake" / "articles",
        project_dir / "content",
        active,
    )
    updated_plan = update_site_plan_with_growth(site_plan, active)
    write_json(site_plan_path, updated_plan)
    reconcile_homepage_guide_links(project_dir / "intake", updated_plan)
    validate_articles(project_dir / "intake" / "articles", ["en"])

    had_site = (project_dir / "package.json").is_file()
    sync_template_source(ROOT / "template", project_dir)
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise PipelineError("npm was not found on PATH; Node.js 20–24 is required.")
    if not (project_dir / "node_modules").is_dir():
        run_command(
            [npm, "ci"],
            cwd=project_dir,
            env=env,
            log_path=logs_dir / "npm-install.log",
            run_log_path=run_log_path,
        )
    run_command(
        [npm, "run", "launch:site"],
        cwd=project_dir,
        env=env,
        log_path=logs_dir / "site-launch.log",
        run_log_path=run_log_path,
    )

    publish_receipt: dict[str, Any] = {}
    if normalized["publish"]:
        command = [sys.executable, str(ROOT / "gamewiki.py"), "publish", normalized["slug"]]
        if normalized.get("githubRepo"):
            command.extend(["--repo", normalized["githubRepo"]])
        if normalized.get("siteUrl"):
            command.extend(["--site-url", normalized["siteUrl"]])
        run_command(
            command,
            cwd=ROOT,
            env=env,
            log_path=logs_dir / "publish.log",
            run_log_path=run_log_path,
        )
        publish_json = project_dir / ".gamewiki" / "publish.json"
        if publish_json.is_file():
            publish_receipt = read_json(publish_json)

    result = {
        "taskType": "siteGrowthContent",
        "slug": normalized["slug"],
        "source": normalized["source"],
        "siteRefreshed": had_site,
        "addedArticles": added,
        "skippedProposals": skipped,
        "publish": normalized["publish"],
        "github": (publish_receipt.get("stages") or {}).get("github"),
        "hosting": (publish_receipt.get("stages") or {}).get("hosting"),
        "onlineVerification": (publish_receipt.get("stages") or {}).get("onlineVerification"),
        "runLog": str(run_log_path),
    }
    write_json(state_dir / "result.json", result)
    if result_path:
        write_json(result_path, result)
    return result


def growth_content_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gamewiki.py growth-content")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args(argv)
    try:
        result = run_growth_content(read_json(args.config), result_path=args.result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"[failed] growth content failed: {exc}", file=sys.stderr)
        return 1

