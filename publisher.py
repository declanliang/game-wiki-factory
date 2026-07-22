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

from orchestrate_wiki import build_subprocess_env, read_json, write_json


ROOT = Path(__file__).resolve().parent
PROJECTS_ROOT = Path(os.environ.get("GAMEWIKI_PROJECTS_ROOT", ROOT.parent)).expanduser().resolve()


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


def _publish_with_vercel_cli(project: Path, project_name: str, full_repo: str, env: dict[str, str]) -> dict:
    vercel = shutil.which("vercel.cmd") or shutil.which("vercel")
    if not vercel:
        raise RuntimeError("VERCEL_TOKEN is absent and no authenticated Vercel CLI was found")
    _run([vercel, "link", "--yes", "--project", project_name], project, env)
    # `vercel link` normally connects an existing Git remote automatically. An
    # explicit connect is safe to skip when Vercel reports it is already linked.
    connected = subprocess.run(
        [vercel, "git", "connect", f"https://github.com/{full_repo}", "--non-interactive"],
        cwd=project,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if connected.returncode and "already" not in (connected.stdout + connected.stderr).casefold():
        raise RuntimeError((connected.stderr or connected.stdout).strip())
    return {
        "status": "awaiting_domain_configuration",
        "projectName": project_name,
        "requiredEnvironmentVariables": ["NEXT_PUBLIC_SITE_URL"],
        "nextAction": "Set the final custom domain and NEXT_PUBLIC_SITE_URL in Vercel, then run npm run verify:deploy.",
        "dashboardUrl": "https://vercel.com/dashboard",
        "updatedAt": _now(),
    }


def _set_vercel_site_url(
    project: Path,
    project_name: str,
    site_url: str,
    env: dict[str, str] | None = None,
) -> str:
    """Set the public canonical origin only when the operator supplied it explicitly."""
    configured = site_url.strip()
    if not re.match(r"^https?://", configured, flags=re.I):
        configured = f"https://{configured}"
    parsed = urllib.parse.urlparse(configured)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("--site-url must be a valid hostname or HTTP(S) URL")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    vercel = shutil.which("vercel.cmd") or shutil.which("vercel")
    if not vercel:
        raise RuntimeError("Vercel CLI is required when --site-url is supplied")
    command_env = env or dict(os.environ)
    # Vercel CLI natively consumes VERCEL_TOKEN.  Never append it to argv:
    # command-line arguments are visible to other users through the process list.
    _run([vercel, "link", "--yes", "--project", project_name], project, command_env)
    _run(
        [vercel, "env", "add", "NEXT_PUBLIC_SITE_URL", "production", "--value", origin,
         "--force", "--yes", "--no-sensitive"],
        project,
        command_env,
    )
    return origin


def _deploy_with_vercel_cli(project: Path, project_name: str, env: dict[str, str]) -> str:
    """Create a production deployment after linking and environment setup."""
    vercel = shutil.which("vercel.cmd") or shutil.which("vercel")
    if not vercel:
        raise RuntimeError("Vercel CLI is required to create the production deployment")
    _run([vercel, "link", "--yes", "--project", project_name], project, env)
    output = _run([vercel, "--prod", "--yes"], project, env)
    urls = re.findall(r"https://[^\s]+", output)
    return urls[-1].rstrip(".,") if urls else ""


def _ensure_private_github_repo(full_repo: str, project: Path, env: dict[str, str]) -> None:
    """Enforce the factory's private-only repository contract before any update push."""
    visibility = _run(
        ["gh", "repo", "view", full_repo, "--json", "visibility", "--jq", ".visibility"],
        project,
        env,
    ).strip().upper()
    if visibility != "PRIVATE":
        _run(
            [
                "gh",
                "repo",
                "edit",
                full_repo,
                "--visibility",
                "private",
                "--accept-visibility-change-consequences",
            ],
            project,
            env,
        )
        visibility = _run(
            ["gh", "repo", "view", full_repo, "--json", "visibility", "--jq", ".visibility"],
            project,
            env,
        ).strip().upper()
    if visibility != "PRIVATE":
        raise RuntimeError(f"GitHub repository visibility must be PRIVATE: {full_repo}")


def _vercel_project_payload(project_name: str, full_repo: str) -> dict:
    """Create only the Vercel project link; domain configuration belongs to the operator."""
    return {
        "name": project_name,
        "framework": "nextjs",
        "gitRepository": {"type": "github", "repo": full_repo},
    }


def _resolve_git_author(project: Path, env: dict[str, str]) -> tuple[str, str]:
    """Return a Vercel-recognizable author without exposing the GitHub token."""
    name = env.get("FACTORY_GIT_AUTHOR_NAME", "").strip()
    email = env.get("FACTORY_GIT_AUTHOR_EMAIL", "").strip()
    if name and email:
        return name, email
    identity = _run(["gh", "api", "user", "--jq", "[.login,.id]|@tsv"], project, env).strip().split("\t")
    if len(identity) != 2 or not identity[0] or not identity[1].isdigit():
        raise RuntimeError("Could not resolve the authenticated GitHub user for commit attribution")
    login, user_id = identity
    return name or login, email or f"{user_id}+{login}@users.noreply.github.com"


def _commit(project: Path, message: str, env: dict[str, str], author: tuple[str, str]) -> None:
    name, email = author
    _run(["git", "-c", f"user.name={name}", "-c", f"user.email={email}", "commit", "-m", message], project, env)


def _replace_remote_main(project: Path, full_repo: str, env: dict[str, str], author: tuple[str, str]) -> str:
    """Replace remote tracked content with one clean generated commit, preserving a backup tag."""
    _run(["git", "fetch", "origin", "main"], project, env)
    remote_sha = _run(["git", "rev-parse", "refs/remotes/origin/main"], project, env)
    backup_tag = f"pre-rebuild-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    _run(["git", "tag", backup_tag, remote_sha], project, env)
    _run(["git", "push", "origin", f"refs/tags/{backup_tag}"], project, env)
    branch = f"factory-rebuild-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    _run(["git", "checkout", "--orphan", branch], project, env)
    subprocess.run(["git", "rm", "--cached", "-r", "--ignore-unmatch", "."], cwd=project, env=env, capture_output=True)
    _run(["git", "add", "--all"], project, env)
    _commit(project, "Rebuild game wiki from latest factory", env, author)
    _run(["git", "branch", "-M", "main"], project, env)
    _run(["git", "push", "--force-with-lease=main:" + remote_sha, "-u", "origin", "main"], project, env)
    return backup_tag


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
    runtime_env = build_subprocess_env(ROOT)
    parser = argparse.ArgumentParser(prog="gamewiki.py publish")
    parser.add_argument("slug")
    parser.add_argument("--owner", default=runtime_env.get("FACTORY_GITHUB_OWNER") or "declanliang")
    parser.add_argument("--repo")
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument("--site-url", help="Optional final domain/URL to configure in Vercel.")
    parser.add_argument("--skip-vercel", action="store_true")
    parser.add_argument("--replace-existing", action="store_true", help="Replace an existing repository tree after creating a backup tag.")
    parser.add_argument("--vercel-project", help="Reuse a Vercel project name that differs from the GitHub repository name.")
    args = parser.parse_args(argv)
    project = (args.project_dir or (PROJECTS_ROOT / args.slug)).expanduser().resolve()
    _validate_project(project)
    repo = args.repo or args.slug
    receipt_path = project / ".gamewiki" / "publish.json"
    receipt = read_json(receipt_path) if receipt_path.is_file() else {"schemaVersion": 1, "slug": args.slug, "createdAt": _now(), "stages": {}}

    gh_token = runtime_env.get("FACTORY_GITHUB_TOKEN") or runtime_env.get("GH_TOKEN")
    if not shutil.which("gh"):
        raise RuntimeError("GitHub CLI (gh) is required for credential-safe publishing")
    env = dict(runtime_env)
    if gh_token:
        env["GH_TOKEN"] = gh_token
    else:
        # Local operators commonly authenticate once with `gh auth login`.
        # Reuse that credential store when no explicit automation token exists.
        _run(["gh", "auth", "status"], project, env)
    author = _resolve_git_author(project, env)
    full_repo = f"{args.owner}/{repo}"
    exists = subprocess.run(["gh", "repo", "view", full_repo], cwd=project, env=env, capture_output=True).returncode == 0
    if not (project / ".git").is_dir():
        _run(["git", "init", "-b", "main"], project)
    if not exists:
        _run(["git", "add", "--all"], project)
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=project).returncode != 0:
            _commit(project, "Generate game wiki site", env, author)
        _run(["gh", "repo", "create", full_repo, "--private", "--source", ".", "--remote", "origin", "--push"], project, env)
    else:
        _ensure_private_github_repo(full_repo, project, env)
        remotes = _run(["git", "remote"], project).splitlines()
        if "origin" not in remotes:
            _run(["git", "remote", "add", "origin", f"https://github.com/{full_repo}.git"], project)
        _run(["gh", "auth", "setup-git"], project, env)
        if args.replace_existing:
            backup_tag = _replace_remote_main(project, full_repo, env, author)
            receipt["backupTag"] = backup_tag
        else:
            _run(["git", "add", "--all"], project)
            if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=project).returncode != 0:
                _commit(project, "Generate game wiki site", env, author)
            _run(["git", "push", "-u", "origin", "main"], project, env)
    _ensure_private_github_repo(full_repo, project, env)
    receipt["stages"]["github"] = {
        "status": "complete",
        "visibility": "PRIVATE",
        "repo": full_repo,
        "url": f"https://github.com/{full_repo}",
        "commit": _run(["git", "rev-parse", "HEAD"], project),
        "updatedAt": _now(),
    }
    write_json(receipt_path, receipt)

    if not args.skip_vercel:
        vercel_token = runtime_env.get("VERCEL_TOKEN")
        project_name = args.vercel_project or re.sub(r"[^a-z0-9-]+", "-", repo.casefold()).strip("-")[:100]
        if vercel_token:
            team_id = runtime_env.get("VERCEL_TEAM_ID", "").strip()
            query = f"?teamId={urllib.parse.quote(team_id)}" if team_id else ""
            try:
                vercel = _request("GET", f"https://api.vercel.com/v9/projects/{project_name}{query}", vercel_token)
            except RuntimeError as exc:
                if "HTTP 404" not in str(exc):
                    raise
                vercel = _request(
                    "POST",
                    f"https://api.vercel.com/v11/projects{query}",
                    vercel_token,
                    _vercel_project_payload(project_name, full_repo),
                )
            receipt["stages"]["vercel"] = {
                "status": "awaiting_domain_configuration",
                "projectId": vercel.get("id"),
                "projectName": vercel.get("name", project_name),
                "requiredEnvironmentVariables": ["NEXT_PUBLIC_SITE_URL"],
                "nextAction": "Set the final custom domain and NEXT_PUBLIC_SITE_URL in Vercel, then run npm run verify:deploy.",
                "dashboardUrl": "https://vercel.com/dashboard",
                "updatedAt": _now(),
            }
        else:
            receipt["stages"]["vercel"] = _publish_with_vercel_cli(project, project_name, full_repo, env)
        if args.site_url:
            configured_origin = _set_vercel_site_url(project, project_name, args.site_url, env)
            receipt["stages"]["vercel"].update({
                "status": "configured",
                "siteUrl": configured_origin,
                "requiredEnvironmentVariables": [],
                "nextAction": "Trigger a production deployment, then run npm run verify:deploy.",
                "updatedAt": _now(),
            })
        deployment_url = _deploy_with_vercel_cli(project, project_name, env)
        receipt["stages"]["vercel"].update({
            "status": "complete",
            "deploymentUrl": deployment_url,
            "nextAction": "Add or verify the custom domain in Vercel when one is planned.",
            "updatedAt": _now(),
        })
        write_json(receipt_path, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0
