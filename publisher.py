"""Idempotently publish a completed generated project to GitHub and Cloudflare Pages."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
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


def _normalize_origin(value: str) -> str:
    configured = value.strip()
    if not re.match(r"^https?://", configured, flags=re.I):
        configured = f"https://{configured}"
    parsed = urllib.parse.urlparse(configured)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("site URL must be a valid hostname or HTTP(S) URL")
    return f"{parsed.scheme}://{parsed.netloc}"


def _cloudflare_credentials(env: dict[str, str]) -> tuple[str, str]:
    account_id = next(
        (env.get(name, "").strip() for name in (
            "CLOUDFLARE_ACCOUNT_ID", "CF_ACCOUNT_ID", "cf_accountid",
        ) if env.get(name, "").strip()),
        "",
    )
    token = next(
        (env.get(name, "").strip() for name in (
            "CLOUDFLARE_API_TOKEN", "CF_PAGES_API_TOKEN", "cf_pages_api_key",
        ) if env.get(name, "").strip()),
        "",
    )
    if not account_id or not token:
        raise RuntimeError(
            "Cloudflare Pages publishing requires CLOUDFLARE_ACCOUNT_ID and "
            "CLOUDFLARE_API_TOKEN (legacy cf_accountid/cf_pages_api_key are also accepted)"
        )
    return account_id, token


def _cloudflare_request(
    method: str,
    account_id: str,
    token: str,
    path: str,
    payload: dict | None = None,
) -> object:
    envelope = _request(
        method,
        f"https://api.cloudflare.com/client/v4/accounts/{urllib.parse.quote(account_id)}/{path.lstrip('/')}",
        token,
        payload,
    )
    if not envelope.get("success", False):
        errors = envelope.get("errors") or []
        summary = "; ".join(str(item.get("message") or item.get("code") or "unknown error") for item in errors[:3])
        raise RuntimeError(f"Cloudflare API request failed: {summary or 'unknown error'}")
    return envelope.get("result")


def _cloudflare_create_git_deployment(
    account_id: str,
    token: str,
    project_name: str,
    branch: str = "main",
) -> dict:
    boundary = f"gamewiki-{int(time.time() * 1000)}"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="branch"\r\n\r\n'
        f"{branch}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{urllib.parse.quote(account_id)}/pages/projects/"
        f"{urllib.parse.quote(project_name)}/deployments",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            envelope = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(
            f"HTTP {exc.code} while triggering Cloudflare Pages Git deployment: {detail}"
        ) from exc
    if not envelope.get("success", False):
        errors = envelope.get("errors") or []
        summary = "; ".join(
            str(item.get("message") or item.get("code") or "unknown error")
            for item in errors[:3]
        )
        raise RuntimeError(
            f"Cloudflare Pages Git deployment request failed: {summary or 'unknown error'}"
        )
    deployment = envelope.get("result")
    if not isinstance(deployment, dict):
        raise RuntimeError("Cloudflare Pages Git deployment response was not an object")
    return deployment


def _cloudflare_git_project_payload(
    project_name: str,
    full_repo: str,
) -> dict:
    owner, repo_name = full_repo.split("/", 1)
    return {
        "name": project_name,
        "production_branch": "main",
        "source": {
            "type": "github",
            "config": {
                "owner": owner,
                "repo_name": repo_name,
                "production_branch": "main",
                "production_deployments_enabled": True,
                "preview_deployment_setting": "none",
                "pr_comments_enabled": False,
            },
        },
        "build_config": {
            "build_command": "npm run build",
            "destination_dir": "out",
            "root_dir": "",
        },
    }


def _validate_cloudflare_git_project(project: dict, full_repo: str) -> None:
    owner, repo_name = full_repo.split("/", 1)
    source = project.get("source")
    if not isinstance(source, dict):
        raise RuntimeError(
            f"Cloudflare Pages project {project.get('name')!r} is a Direct Upload project; "
            "existing projects are never converted or replaced automatically"
        )
    config = source.get("config") or {}
    actual = (
        str(source.get("type") or "").casefold(),
        str(config.get("owner") or "").casefold(),
        str(config.get("repo_name") or "").casefold(),
        str(config.get("production_branch") or project.get("production_branch") or "").casefold(),
    )
    expected = ("github", owner.casefold(), repo_name.casefold(), "main")
    if actual != expected:
        raise RuntimeError(
            f"Cloudflare Pages project {project.get('name')!r} is connected to a different "
            "Git source or production branch"
        )
    build = project.get("build_config") or {}
    if (
        str(build.get("build_command") or "") != "npm run build"
        or str(build.get("destination_dir") or "").strip("/") != "out"
        or str(build.get("root_dir") or "") not in {"", "/"}
    ):
        raise RuntimeError(
            f"Cloudflare Pages project {project.get('name')!r} has an incompatible build configuration"
        )


def _ensure_cloudflare_project(
    account_id: str,
    token: str,
    project_name: str,
    full_repo: str,
) -> tuple[dict, bool]:
    encoded_name = urllib.parse.quote(project_name)
    created = False
    try:
        project = _cloudflare_request(
            "GET", account_id, token, f"pages/projects/{encoded_name}"
        )
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise
        project = _cloudflare_request(
            "POST",
            account_id,
            token,
            "pages/projects",
            _cloudflare_git_project_payload(project_name, full_repo),
        )
        created = True
    if not isinstance(project, dict):
        raise RuntimeError("Cloudflare Pages project response was not an object")
    _validate_cloudflare_git_project(project, full_repo)
    return project, created


def _cloudflare_git_authorization_error(exc: RuntimeError) -> RuntimeError:
    folded = str(exc).casefold()
    if any(marker in folded for marker in (
        "repository not found",
        "repo not found",
        "not authorized",
        "not authorised",
        "github installation",
        "github app",
        "could not access",
    )):
        return RuntimeError(
            "Cloudflare Pages could not access the new Private GitHub repository. "
            "Grant the Cloudflare Workers & Pages GitHub App access to the repository "
            "(prefer All repositories for unattended future jobs), then retry the same Job."
        )
    return exc


def _resolve_cloudflare_project(
    account_id: str,
    token: str,
    project_name: str,
    full_repo: str,
) -> tuple[str, dict, bool]:
    """Resolve a Git-integrated project, with a deterministic name fallback.

    Cloudflare can return error 8000000/HTTP 500 for an otherwise valid Pages
    name that it cannot allocate. A suffixed name is safe because the Factory
    records the actual Pages project and the canonical URL remains independent.
    """
    try:
        project, created = _ensure_cloudflare_project(
            account_id, token, project_name, full_repo
        )
        return project_name, project, created
    except RuntimeError as exc:
        message = str(exc)
        if "HTTP 500" not in message or '"code": 8000000' not in message:
            raise _cloudflare_git_authorization_error(exc) from exc
        fallback_name = f"{project_name}-wiki"
        try:
            project, created = _ensure_cloudflare_project(
                account_id, token, fallback_name, full_repo
            )
        except RuntimeError as fallback_exc:
            raise _cloudflare_git_authorization_error(fallback_exc) from fallback_exc
        return fallback_name, project, created


def _set_cloudflare_site_url(
    account_id: str,
    token: str,
    project_name: str,
    origin: str,
    cloudflare_project: dict,
    *,
    created: bool,
) -> bool:
    production = (
        (cloudflare_project.get("deployment_configs") or {}).get("production") or {}
    )
    env_vars = production.get("env_vars") or {}
    current = env_vars.get("NEXT_PUBLIC_SITE_URL") or {}
    if (
        str(current.get("type") or "") == "plain_text"
        and str(current.get("value") or "").rstrip("/") == origin.rstrip("/")
    ):
        return False
    unrelated = sorted(key for key in env_vars if key != "NEXT_PUBLIC_SITE_URL")
    if unrelated and not created:
        raise RuntimeError(
            "Refusing to replace Cloudflare Pages Production env_vars while unrelated "
            f"variables exist: {', '.join(unrelated)}. Update them with the dedicated "
            "environment-variable Agent so encrypted values are preserved."
        )
    _cloudflare_request(
        "PATCH",
        account_id,
        token,
        f"pages/projects/{urllib.parse.quote(project_name)}",
        {
            "deployment_configs": {
                "production": {
                    "env_vars": {
                        "NEXT_PUBLIC_SITE_URL": {
                            "type": "plain_text",
                            "value": origin,
                        }
                    }
                }
            }
        },
    )
    return True


def _append_cloudflare_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"[{_now()}] {message.rstrip()}\n")


def _cloudflare_deployment_failure_tail(
    account_id: str,
    token: str,
    project_name: str,
) -> str:
    try:
        history = _cloudflare_request(
            "GET",
            account_id,
            token,
            f"pages/projects/{urllib.parse.quote(project_name)}/deployments",
        )
    except RuntimeError:
        return ""
    if not isinstance(history, list):
        return ""
    failures: list[str] = []
    for deployment in history[:3]:
        stage = deployment.get("latest_stage") or {}
        if str(stage.get("status") or "").casefold() in {"failure", "canceled"}:
            failures.append(
                f"{deployment.get('id') or '<unknown>'}: "
                f"{stage.get('name') or 'unknown'}={stage.get('status') or 'unknown'}"
            )
    return "; ".join(failures)


def _wait_cloudflare_deployment(
    account_id: str,
    token: str,
    project_name: str,
    deployment_id: str,
    commit_sha: str,
    *,
    attempts: int = 120,
    log_path: Path | None = None,
) -> dict:
    encoded_name = urllib.parse.quote(project_name)
    encoded_deployment = urllib.parse.quote(deployment_id)
    deployment: dict | None = None
    last_stage = ""
    for attempt in range(attempts):
        candidate = _cloudflare_request(
            "GET",
            account_id,
            token,
            f"pages/projects/{encoded_name}/deployments/{encoded_deployment}",
        )
        if not isinstance(candidate, dict):
            raise RuntimeError("Cloudflare Pages deployment response was not an object")
        deployment = candidate
        stage = deployment.get("latest_stage") or {}
        stage_summary = f"{stage.get('name') or 'unknown'}={stage.get('status') or 'unknown'}"
        if stage_summary != last_stage and log_path is not None:
            _append_cloudflare_log(log_path, f"deployment {deployment_id}: {stage_summary}")
            last_stage = stage_summary
        status = str(stage.get("status") or "").casefold()
        if status in {"success", "failure", "canceled"}:
            break
        if attempt + 1 < attempts:
            time.sleep(3)
    if not deployment:
        raise RuntimeError(
            f"Cloudflare Pages deployment {deployment_id} was not returned by the API"
        )
    status = str((deployment.get("latest_stage") or {}).get("status") or "").casefold()
    if status != "success":
        detail = _cloudflare_deployment_failure_tail(
            account_id, token, project_name
        )
        raise RuntimeError(
            f"Cloudflare Pages deployment {deployment_id} ended with status "
            f"{status or 'timeout'}{(': ' + detail) if detail else ''}"
        )
    metadata = ((deployment.get("deployment_trigger") or {}).get("metadata") or {})
    deployed_sha = str(metadata.get("commit_hash") or "").casefold()
    expected_sha = commit_sha.casefold()
    if not deployed_sha or not (
        deployed_sha.startswith(expected_sha) or expected_sha.startswith(deployed_sha)
    ):
        raise RuntimeError(
            f"Cloudflare Pages deployed commit {deployed_sha or '<missing>'}, "
            f"expected {expected_sha}"
        )
    return deployment


def _deploy_cloudflare_pages(
    project: Path,
    project_name: str,
    full_repo: str,
    site_url: str,
    commit_sha: str,
    env: dict[str, str],
) -> dict:
    account_id, token = _cloudflare_credentials(env)
    project_name, cloudflare_project, created = _resolve_cloudflare_project(
        account_id, token, project_name, full_repo
    )
    subdomain = str(cloudflare_project.get("subdomain") or f"{project_name}.pages.dev").strip()
    pages_origin = _normalize_origin(subdomain)
    canonical_origin = _normalize_origin(site_url) if site_url.strip() else pages_origin
    log_path = project / ".gamewiki" / "logs" / "cloudflare-pages-publish.log"
    _append_cloudflare_log(
        log_path,
        f"resolved Git-integrated project {project_name} for {full_repo}; created={created}",
    )
    changed = _set_cloudflare_site_url(
        account_id,
        token,
        project_name,
        canonical_origin,
        cloudflare_project,
        created=created,
    )
    _append_cloudflare_log(
        log_path,
        f"Production NEXT_PUBLIC_SITE_URL {'updated' if changed else 'already matched'}",
    )
    deployment = _cloudflare_create_git_deployment(
        account_id, token, project_name, "main"
    )
    if not isinstance(deployment, dict) or not deployment.get("id"):
        raise RuntimeError("Cloudflare Pages did not return an initial deployment ID")
    deployment_id = str(deployment["id"])
    _append_cloudflare_log(
        log_path,
        f"triggered Git deployment {deployment_id} from main",
    )
    deployment = _wait_cloudflare_deployment(
        account_id,
        token,
        project_name,
        deployment_id,
        commit_sha,
        log_path=log_path,
    )
    deployment_url = str(deployment.get("url") or "").rstrip("/")
    return {
        "provider": "cloudflare-pages",
        "status": "deployed",
        "projectId": cloudflare_project.get("id"),
        "projectName": cloudflare_project.get("name") or project_name,
        "productionBranch": "main",
        "deploymentId": deployment.get("id"),
        "deploymentUrl": deployment_url,
        "pagesOrigin": pages_origin,
        "siteUrl": canonical_origin,
        "environmentVariables": ["NEXT_PUBLIC_SITE_URL"],
        "deploymentMode": "git-integration",
        "source": {
            "type": "github",
            "repo": full_repo,
            "productionBranch": "main",
        },
        "buildConfig": {
            "command": "npm run build",
            "destination": "out",
            "root": "",
        },
        "log": str(log_path),
        "updatedAt": _now(),
    }


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
    urls = [item.rstrip(".,)") for item in re.findall(r"https://[^\s\"']+", output)]
    public_urls = [
        item for item in urls
        if (urllib.parse.urlparse(item).hostname or "").casefold() != "api.vercel.com"
    ]
    deployment_urls = [
        item for item in public_urls
        if (urllib.parse.urlparse(item).hostname or "").casefold().endswith(".vercel.app")
    ]
    return deployment_urls[-1] if deployment_urls else ""


def _verify_online_deployment(project: Path, origin: str, env: dict[str, str]) -> dict:
    """Make remote SEO/runtime verification a publish postcondition."""
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise RuntimeError("npm is required for online deployment verification")
    normalized = origin.strip().rstrip("/")
    parsed = urllib.parse.urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("online verification requires a valid HTTP(S) production origin")
    verify_env = dict(env)
    verify_env["NEXT_PUBLIC_SITE_URL"] = f"{parsed.scheme}://{parsed.netloc}"
    # Rebuild with the final public origin.  The generation build may have used
    # example.com intentionally, while Vercel injects its production env only in
    # the remote build.  Reusing that local artifact would create false failures
    # and would not prove the final-origin build itself is healthy.
    command = [npm, "run", "verify:deploy"]
    result = subprocess.run(
        command,
        cwd=project,
        env=verify_env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    output = (result.stdout or "") + (result.stderr or "")
    log_path = project / ".gamewiki" / "deploy-verification.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output, encoding="utf-8")
    if result.returncode:
        tail = output[-2000:].strip()
        raise RuntimeError(
            f"online deployment verification failed for {verify_env['NEXT_PUBLIC_SITE_URL']}; "
            f"see {log_path}{(': ' + tail) if tail else ''}"
        )
    return {
        "status": "complete",
        "origin": verify_env["NEXT_PUBLIC_SITE_URL"],
        "checks": [
            "home metadata", "canonical", "sitemap", "robots",
            "all sitemap loc/hreflang targets direct 200",
        ],
        "log": str(log_path),
        "checkedAt": _now(),
    }


class _CanonicalParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.canonical = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "link":
            return
        values = {key.casefold(): value or "" for key, value in attrs}
        if "canonical" in values.get("rel", "").casefold().split():
            self.canonical = values.get("href", "")


def _custom_origin_is_ready(origin: str) -> bool:
    expected = f"{origin.rstrip('/')}/en"
    try:
        request = urllib.request.Request(expected, headers={"User-Agent": "GameWikiFactory/1.0"})
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                return False
            parser = _CanonicalParser()
            parser.feed(response.read().decode("utf-8", errors="replace"))
            return parser.canonical.rstrip("/") == expected
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


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
    for relative in ("package.json", "intake/site-identity.json", "intake/site-content.json", "intake/site-plan.json", "intake/factory-release.json"):
        if not (project / relative).is_file():
            raise RuntimeError(f"Required publish file is missing: {relative}")
    expected_release = str(read_json(ROOT / "release.json").get("release") or "").strip()
    stamped_release = str(read_json(project / "intake" / "factory-release.json").get("release") or "").strip()
    if not expected_release or stamped_release != expected_release:
        raise RuntimeError(
            f"Project is not certified for the current Factory release: expected {expected_release!r}, got {stamped_release!r}"
        )
    forbidden_names = {".env", ".env.local", ".env.production"}
    for path in project.rglob("*"):
        if ".git" in path.parts or "node_modules" in path.parts or ".gamewiki" in path.parts:
            continue
        if path.is_file() and (path.name in forbidden_names or re.search(r"(?:API_KEY|TOKEN|PASSWORD)\s*=\s*[^\s#]+", path.read_text(encoding="utf-8", errors="ignore"))):
            raise RuntimeError(f"Secret-like file/content blocks publishing: {path.relative_to(project)}")
    return manifest


def _remove_vercel_oidc_env(project: Path) -> bool:
    """Remove only the one-key temporary file created by recent Vercel CLI releases."""
    path = project / ".env.local"
    if not path.is_file():
        return False
    keys: set[str] = set()
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            return False
        keys.add(line.split("=", 1)[0].strip())
    if keys != {"VERCEL_OIDC_TOKEN"}:
        return False
    path.unlink()
    return True


def publish(argv: list[str]) -> int:
    runtime_env = build_subprocess_env(ROOT)
    parser = argparse.ArgumentParser(prog="gamewiki.py publish")
    parser.add_argument("slug")
    parser.add_argument("--owner", default=runtime_env.get("FACTORY_GITHUB_OWNER") or "declanliang")
    parser.add_argument("--repo")
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument("--site-url", help="Optional final canonical domain/URL for Cloudflare Pages.")
    parser.add_argument("--skip-cloudflare", action="store_true")
    parser.add_argument("--skip-vercel", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--replace-existing", action="store_true", help="Replace an existing repository tree after creating a backup tag.")
    parser.add_argument("--vercel-project", help="Reuse a Vercel project name that differs from the GitHub repository name.")
    args = parser.parse_args(argv)
    project = (args.project_dir or (PROJECTS_ROOT / args.slug)).expanduser().resolve()
    _remove_vercel_oidc_env(project)
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

    if args.skip_cloudflare or args.skip_vercel:
        receipt["stages"]["hosting"] = {
            "provider": "cloudflare-pages",
            "status": "manual_action_required",
            "nextAction": "Create a Cloudflare Pages project, set NEXT_PUBLIC_SITE_URL, deploy, and run npm run verify:deploy.",
            "dashboardUrl": "https://dash.cloudflare.com/",
            "updatedAt": _now(),
        }
        receipt["stages"].pop("vercel", None)
        receipt["stages"].pop("onlineVerification", None)
        write_json(receipt_path, receipt)
    else:
        project_name = re.sub(r"[^a-z0-9-]+", "-", repo.casefold()).strip("-")[:58]
        hosting = _deploy_cloudflare_pages(
            project,
            project_name,
            full_repo,
            args.site_url or "",
            receipt["stages"]["github"]["commit"],
            env,
        )
        hosting.update({
            "status": "verifying",
            "dashboardUrl": "https://dash.cloudflare.com/",
            "nextAction": "Automated deployment verification is running.",
            "updatedAt": _now(),
        })
        receipt["stages"]["hosting"] = hosting
        receipt["stages"].pop("vercel", None)
        receipt["stages"]["onlineVerification"] = {
            "status": "running",
            "origin": hosting["siteUrl"],
            "updatedAt": _now(),
        }
        write_json(receipt_path, receipt)

        custom_domain_pending = (
            hosting["siteUrl"] != hosting["pagesOrigin"]
            and not _custom_origin_is_ready(hosting["siteUrl"])
        )
        if custom_domain_pending:
            receipt["stages"]["onlineVerification"] = {
                "status": "awaiting_domain_configuration",
                "origin": hosting["siteUrl"],
                "deploymentUrl": hosting["deploymentUrl"],
                "nextAction": "Bind the custom domain in Cloudflare Pages, then run npm run verify:deploy.",
                "updatedAt": _now(),
            }
            receipt["stages"]["hosting"].update({
                "status": "awaiting_domain_configuration",
                "nextAction": "Pages deployment is complete. Bind the custom domain; NEXT_PUBLIC_SITE_URL is already configured.",
                "updatedAt": _now(),
            })
        else:
            verification = _verify_online_deployment(project, hosting["siteUrl"], env)
            receipt["stages"]["onlineVerification"] = verification
            receipt["stages"]["hosting"].update({
                "status": "complete",
                "nextAction": "Cloudflare Pages production deployment and online verification are complete.",
                "updatedAt": _now(),
            })
        write_json(receipt_path, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0
