"""Publish one scheduled locale by committing the publication plan to GitHub."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from orchestrate_wiki import ROOT, build_subprocess_env, read_json, write_json
from publication_plan import next_locale, validate_publication_plan
from publisher import (
    _cloudflare_credentials,
    _deploy_cloudflare_workers_static_assets,
    _ensure_workers_static_assets_runtime,
    _normalize_origin,
    _npm_binary,
    _run_logged,
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _github_token(env: dict[str, str]) -> str:
    token = (env.get("FACTORY_GITHUB_TOKEN") or env.get("GH_TOKEN") or "").strip()
    if token:
        return token
    if not shutil.which("gh"):
        raise RuntimeError("GitHub authentication is required for scheduled locale release")
    result = subprocess.run(
        ["gh", "auth", "token"],
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    token = result.stdout.strip()
    if result.returncode or not token:
        raise RuntimeError("Could not obtain the authenticated GitHub token")
    return token


def _github_request(
    method: str,
    token: str,
    path: str,
    payload: dict | None = None,
) -> object:
    request = urllib.request.Request(
        f"https://api.github.com/{path.lstrip('/')}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "GameWikiFactory/1.0",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"GitHub API HTTP {exc.code} for {path}: {detail}") from exc


def _decode_github_content(response: object) -> tuple[dict, str]:
    if not isinstance(response, dict):
        raise RuntimeError("GitHub publication-plan response was not an object")
    encoded = str(response.get("content") or "").replace("\n", "")
    blob_sha = str(response.get("sha") or "")
    if not encoded or not blob_sha:
        raise RuntimeError("GitHub publication-plan response omitted content or sha")
    try:
        value = json.loads(base64.b64decode(encoded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("GitHub publication-plan.json is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("GitHub publication-plan.json must contain an object")
    return value, blob_sha


def _latest_path_commit(token: str, repo: str) -> str:
    response = _github_request(
        "GET",
        token,
        f"repos/{repo}/commits?sha=main&path=intake/publication-plan.json&per_page=1",
    )
    if not isinstance(response, list) or not response:
        raise RuntimeError("Could not resolve the latest publication-plan commit")
    commit_sha = str(response[0].get("sha") or "")
    if not commit_sha:
        raise RuntimeError("Latest publication-plan commit omitted its sha")
    return commit_sha


def publish_locale_in_github(token: str, repo: str, locale: str) -> tuple[dict, str, bool]:
    """Atomically append exactly one locale and return plan, commit SHA, changed."""
    encoded_repo = "/".join(urllib.parse.quote(part) for part in repo.split("/", 1))
    path = f"repos/{encoded_repo}/contents/intake/publication-plan.json"
    response = _github_request("GET", token, f"{path}?ref=main")
    plan, blob_sha = _decode_github_content(response)
    validate_publication_plan(plan)
    published = list(plan["publishedLocales"])
    if locale in published:
        return plan, _latest_path_commit(token, encoded_repo), False
    expected = next_locale(published)
    if locale != expected:
        raise RuntimeError(
            f"Locale release order violation: expected {expected or 'no further locale'}, got {locale}"
        )
    plan["publishedLocales"] = [*published, locale]
    plan["updatedAt"] = _now()
    content = base64.b64encode(
        (json.dumps(plan, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    ).decode("ascii")
    updated = _github_request(
        "PUT",
        token,
        path,
        {
            "message": f"Release {locale} locale",
            "content": content,
            "sha": blob_sha,
            "branch": "main",
        },
    )
    if not isinstance(updated, dict):
        raise RuntimeError("GitHub locale release response was not an object")
    commit_sha = str((updated.get("commit") or {}).get("sha") or "")
    if not commit_sha:
        raise RuntimeError("GitHub locale release response omitted commit sha")
    return plan, commit_sha, True


def _clone_locale_release_workspace(
    repo: str,
    commit_sha: str,
    env: dict[str, str],
    parent: Path,
) -> Path:
    project = parent / repo.rsplit("/", 1)[-1]
    clone_log_path = parent / "locale-release-workers-clone.log"
    _run_logged(
        ["gh", "repo", "clone", repo, str(project), "--", "--branch", "main"],
        ROOT,
        env,
        clone_log_path,
        "clone locale release repository",
    )
    log_path = project / ".gamewiki" / "logs" / "locale-release-workers.log"
    _run_logged(
        ["git", "checkout", commit_sha],
        project,
        env,
        log_path,
        "checkout locale release commit",
    )
    _ensure_workers_static_assets_runtime(project)
    _run_logged(
        [_npm_binary("npm"), "ci"],
        project,
        env,
        log_path,
        "install locale release dependencies",
    )
    return project


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.description = ""
        self.canonical = ""
        self.hreflangs: set[str] = set()
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        if tag.casefold() == "title":
            self._in_title = True
        elif tag.casefold() == "meta" and values.get("name", "").casefold() == "description":
            self.description = values.get("content", "").strip()
        elif tag.casefold() == "link":
            rel = values.get("rel", "").casefold().split()
            if "canonical" in rel:
                self.canonical = values.get("href", "").rstrip("/")
            if "alternate" in rel and values.get("hreflang"):
                self.hreflangs.add(values["hreflang"].casefold())

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def _fetch(url: str) -> tuple[int, str, dict[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": "GameWikiFactory/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return (
            int(response.status),
            response.read().decode("utf-8", errors="replace"),
            {key.casefold(): value for key, value in response.headers.items()},
        )


def verify_locale_deployment(
    deployment_origin: str,
    canonical_origin: str,
    published_locales: list[str],
) -> dict:
    """Verify active routes and ensure future locales remain absent from SEO output."""
    deployment_origin = _normalize_origin(deployment_origin)
    canonical_origin = _normalize_origin(canonical_origin)
    required_hreflangs = {*published_locales, "x-default"}
    checked: list[str] = []
    for locale in published_locales:
        status, html, _headers = _fetch(f"{deployment_origin}/{locale}")
        if status != 200:
            raise RuntimeError(f"Locale homepage /{locale} returned HTTP {status}")
        parser = _MetadataParser()
        parser.feed(html)
        expected_canonical = f"{canonical_origin}/{locale}".rstrip("/")
        if not parser.title.strip() or not parser.description:
            raise RuntimeError(f"Locale homepage /{locale} is missing title or description")
        if parser.canonical != expected_canonical:
            raise RuntimeError(
                f"Locale homepage /{locale} canonical is {parser.canonical or '<missing>'}, "
                f"expected {expected_canonical}"
            )
        if parser.hreflangs != required_hreflangs:
            raise RuntimeError(
                f"Locale homepage /{locale} hreflang set is {sorted(parser.hreflangs)}, "
                f"expected {sorted(required_hreflangs)}"
            )
        checked.append(f"/{locale}")

    status, sitemap_xml, _headers = _fetch(f"{deployment_origin}/sitemap.xml")
    if status != 200:
        raise RuntimeError(f"sitemap.xml returned HTTP {status}")
    try:
        root = ElementTree.fromstring(sitemap_xml)
    except ElementTree.ParseError as exc:
        raise RuntimeError("sitemap.xml is not valid XML") from exc
    locs = [
        (node.text or "").strip()
        for node in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
    ]
    alternates = root.findall(".//{http://www.w3.org/1999/xhtml}link")
    sitemap_hreflangs = {
        str(node.attrib.get("hreflang") or "").casefold() for node in alternates
    }
    if sitemap_hreflangs != required_hreflangs:
        raise RuntimeError(
            f"sitemap hreflang set is {sorted(sitemap_hreflangs)}, "
            f"expected {sorted(required_hreflangs)}"
        )
    unpublished = {"en", "es", "de", "fr", "ja"} - set(published_locales)
    for url in locs:
        parsed = urllib.parse.urlparse(url)
        first = parsed.path.split("/", 2)[1] if parsed.path.startswith("/") else ""
        if first in unpublished:
            raise RuntimeError(f"sitemap exposes unpublished locale URL: {url}")
        probe = f"{deployment_origin}{parsed.path}"
        if parsed.query:
            probe += f"?{parsed.query}"
        target_status, _body, _target_headers = _fetch(probe)
        if target_status != 200:
            raise RuntimeError(f"sitemap route {parsed.path} returned HTTP {target_status}")
    checked.extend(["/sitemap.xml", *[urllib.parse.urlparse(url).path for url in locs]])
    return {
        "status": "complete",
        "deploymentOrigin": deployment_origin,
        "canonicalOrigin": canonical_origin,
        "publishedLocales": published_locales,
        "checkedRoutes": len(set(checked)),
        "checkedAt": _now(),
    }


def release_locale(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gamewiki.py release-locale")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args(argv)
    config = read_json(args.config.expanduser().resolve())
    if str(config.get("taskType") or "") != "localeRelease":
        raise RuntimeError("release-locale requires an internal localeRelease config")
    locale = str(config.get("locale") or "").strip().casefold()
    repo = str(config.get("githubRepo") or "").strip()
    project_name = str(config.get("workerName") or config.get("cloudflareProject") or "").strip()
    canonical_origin = str(config.get("siteUrl") or "").strip()
    if locale not in {"es", "de", "fr", "ja"}:
        raise RuntimeError(f"Unsupported scheduled locale: {locale or '<missing>'}")
    if not re.fullmatch(r"[^/]+/[^/]+", repo):
        raise RuntimeError("localeRelease githubRepo must be owner/repository")
    if not project_name or not canonical_origin:
        raise RuntimeError("localeRelease requires Cloudflare Worker name and canonical site URL")

    env = build_subprocess_env(ROOT)
    token = _github_token(env)
    env.setdefault("GH_TOKEN", token)
    plan, commit_sha, changed = publish_locale_in_github(token, repo, locale)
    _cloudflare_credentials(env)
    with tempfile.TemporaryDirectory(prefix="gamewiki-locale-release-") as temporary:
        project = _clone_locale_release_workspace(
            repo,
            commit_sha,
            env,
            Path(temporary),
        )
        hosting = _deploy_cloudflare_workers_static_assets(
            project,
            project_name,
            repo,
            canonical_origin,
            commit_sha,
            env,
        )
    deployment_origin = str(
        hosting.get("deploymentUrl")
        or hosting.get("workersDevOrigin")
        or config.get("workersDevOrigin")
        or ""
    )
    verification = verify_locale_deployment(
        deployment_origin,
        canonical_origin,
        list(plan["publishedLocales"]),
    )
    result = {
        "taskType": "localeRelease",
        "locale": locale,
        "publishedLocales": plan["publishedLocales"],
        "github": {
            "repo": repo,
            "commit": commit_sha,
            "changed": changed,
        },
        "hosting": {
            "provider": "cloudflare-workers-static-assets",
            "projectName": project_name,
            "workerName": project_name,
            "deploymentId": hosting.get("deploymentId"),
            "deploymentUrl": deployment_origin,
            "workersDevOrigin": str(
                hosting.get("workersDevOrigin")
                or config.get("workersDevOrigin")
                or deployment_origin
            ),
            "siteUrl": canonical_origin,
            "deploymentMode": "wrangler-static-assets",
        },
        "onlineVerification": verification,
        "completedAt": _now(),
    }
    write_json(args.result.expanduser().resolve(), result)
    print(
        json.dumps(
            {
                "status": "complete",
                "locale": locale,
                "publishedLocales": plan["publishedLocales"],
                "commit": commit_sha,
            },
            ensure_ascii=False,
        )
    )
    return 0
