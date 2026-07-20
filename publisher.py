"""Idempotently publish a completed generated project to GitHub and Vercel."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from orchestrate_wiki import read_json, write_json


ROOT = Path(__file__).resolve().parent
PROJECTS_ROOT = ROOT.parent


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "command failed").strip())
    return result.stdout.strip()


def _request(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc


def _validate_project(project: Path) -> dict:
    manifest = read_json(project / ".gamewiki" / "manifest.json")
    if manifest.get("status") != "complete":
        raise RuntimeError("Project pipeline manifest is not complete")
    for relative in ("package.json", "intake/site-identity.json", "intake/site-content.json", "intake/site-plan.json"):
        if not (project / relative).is_file():
            raise RuntimeError(f"Required publish file is missing: {relative}")
    forbidden_names = {".env", ".env.local", ".env.production"}
    for path in project.rglob("*"):
        if ".git" in path.parts or "node_modules" in path.parts or ".gamewiki" in path.parts:
            continue
        if path.is_file() and (path.name in forbidden_names or re.search(r"(?:API_KEY|TOKEN|PASSWORD)\s*=\s*[^\s#]+", path.read_text(encoding="utf-8", errors="ignore"))):
            raise RuntimeError(f"Secret-like file/content blocks publishing: {path.relative_to(project)}")
    return manifest


def publish(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gamewiki.py publish")
    parser.add_argument("slug")
    parser.add_argument("--owner", default=os.getenv("FACTORY_GITHUB_OWNER") or "declanliang")
    parser.add_argument("--repo")
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--skip-vercel", action="store_true")
    args = parser.parse_args(argv)
    project = (args.project_dir or (PROJECTS_ROOT / args.slug)).expanduser().resolve()
    _validate_project(project)
    repo = args.repo or args.slug
    receipt_path = project / ".gamewiki" / "publish.json"
    receipt = read_json(receipt_path) if receipt_path.is_file() else {"schemaVersion": 1, "slug": args.slug, "createdAt": _now(), "stages": {}}

    gh_token = os.getenv("FACTORY_GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not gh_token:
        raise RuntimeError("FACTORY_GITHUB_TOKEN (or GH_TOKEN) is required")
    if not shutil.which("gh"):
        raise RuntimeError("GitHub CLI (gh) is required for credential-safe publishing")
    env = dict(os.environ)
    env["GH_TOKEN"] = gh_token
    full_repo = f"{args.owner}/{repo}"
    exists = subprocess.run(["gh", "repo", "view", full_repo], cwd=project, env=env, capture_output=True).returncode == 0
    if not (project / ".git").is_dir():
        _run(["git", "init", "-b", "main"], project)
    _run(["git", "add", "--all"], project)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=project).returncode != 0:
        _run(["git", "-c", "user.name=game-wiki-factory", "-c", "user.email=factory@local.invalid", "commit", "-m", "Generate game wiki site"], project)
    if not exists:
        visibility = "--private" if args.private else "--public"
        _run(["gh", "repo", "create", full_repo, visibility, "--source", ".", "--remote", "origin", "--push"], project, env)
    else:
        remotes = _run(["git", "remote"], project).splitlines()
        if "origin" not in remotes:
            _run(["git", "remote", "add", "origin", f"https://github.com/{full_repo}.git"], project)
        _run(["gh", "auth", "setup-git"], project, env)
        _run(["git", "push", "-u", "origin", "main"], project, env)
    receipt["stages"]["github"] = {
        "status": "complete",
        "repo": full_repo,
        "url": f"https://github.com/{full_repo}",
        "commit": _run(["git", "rev-parse", "HEAD"], project),
        "updatedAt": _now(),
    }
    write_json(receipt_path, receipt)

    if not args.skip_vercel:
        vercel_token = os.getenv("VERCEL_TOKEN")
        if not vercel_token:
            raise RuntimeError("VERCEL_TOKEN is required unless --skip-vercel is used")
        team_id = os.getenv("VERCEL_TEAM_ID", "").strip()
        query = f"?teamId={urllib.parse.quote(team_id)}" if team_id else ""
        project_name = re.sub(r"[^a-z0-9-]+", "-", repo.casefold()).strip("-")[:100]
        try:
            vercel = _request("GET", f"https://api.vercel.com/v9/projects/{project_name}{query}", vercel_token)
        except RuntimeError as exc:
            if "HTTP 404" not in str(exc):
                raise
            vercel = _request("POST", f"https://api.vercel.com/v11/projects{query}", vercel_token, {
                "name": project_name,
                "framework": "nextjs",
                "gitRepository": {"type": "github", "repo": full_repo},
            })
        receipt["stages"]["vercel"] = {
            "status": "complete",
            "projectId": vercel.get("id"),
            "projectName": vercel.get("name", project_name),
            "dashboardUrl": "https://vercel.com/dashboard",
            "updatedAt": _now(),
        }
        write_json(receipt_path, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0
