"""Strict Adsterra import, Vercel configuration, deployment, and verification.

The operator supplies the unmodified JSON exported from Adsterra.  This module
owns title-to-slot mapping and Base64 transport so neither a human nor an Agent
can accidentally put a 160x600 creative in the 320x50 placement.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orchestrate_wiki import build_subprocess_env, read_json, slugify, write_json
from publisher import _deploy_with_vercel_cli


ROOT = Path(__file__).resolve().parent
PROJECTS_ROOT = Path(os.environ.get("GAMEWIKI_PROJECTS_ROOT", ROOT.parent)).expanduser().resolve()


@dataclass(frozen=True)
class PlacementSpec:
    title: str
    env_name: str
    route_format: str
    width: int | None = None
    height: int | None = None


PLACEMENTS = (
    PlacementSpec("Native Banner", "AD_NATIVE_BANNER_B64", "nativeBanner"),
    PlacementSpec("Banner 468x60", "AD_BANNER_468X60_B64", "banner468x60", 468, 60),
    PlacementSpec("Banner 300x250", "AD_BANNER_300X250_B64", "banner300x250", 300, 250),
    PlacementSpec("Banner 160x300", "AD_SIDEBAR_160X300_B64", "sidebar160x300", 160, 300),
    PlacementSpec("Banner 160x600", "AD_SIDEBAR_160X600_B64", "sidebar160x600", 160, 600),
    PlacementSpec("Banner 320x50", "AD_MOBILE_320X50_B64", "mobile320x50", 320, 50),
    PlacementSpec("Banner 728x90", "AD_BANNER_728X90_B64", "banner728x90", 728, 90),
)
PLACEMENT_BY_TITLE = {item.title: item for item in PLACEMENTS}
ALLOWED_TOP_LEVEL = {
    "schemaVersion", "taskType", "game", "domain_id", "domain_name", "placements"
}
ALLOWED_PLACEMENT_FIELDS = {"placement_id", "title", "alias", "code"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _domain(value: str) -> str:
    text = value.strip().casefold()
    if "://" in text:
        text = urllib.parse.urlparse(text).hostname or ""
    return text.rstrip(".")


def _compact_identity(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _http_json(method: str, url: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
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
        raise RuntimeError(f"Vercel API HTTP {exc.code}: {detail}") from exc


def _banner_dimension(code: str, name: str) -> int | None:
    match = re.search(rf"['\"]{name}['\"]\s*:\s*(\d+)", code)
    return int(match.group(1)) if match else None


def _validate_snippet(spec: PlacementSpec, code: str) -> None:
    if "<script" not in code.casefold():
        raise ValueError(f"{spec.title}: code has no script tag")
    sources = re.findall(r"\bsrc\s*=\s*['\"]([^'\"]+)['\"]", code, flags=re.I)
    if len(sources) != 1:
        raise ValueError(f"{spec.title}: expected exactly one external script source")
    source = sources[0]
    source_host = _domain(source)
    if spec.width is None:
        if not source_host.endswith("effectivecpmnetwork.com"):
            raise ValueError(f"{spec.title}: unexpected native-banner script host")
        container = re.search(r"id=['\"]container-([a-z0-9]+)['\"]", code, flags=re.I)
        invoke = re.search(r"/([a-z0-9]+)/invoke\.js(?:\?|$)", source, flags=re.I)
        if not container or not invoke or container.group(1).casefold() != invoke.group(1).casefold():
            raise ValueError(f"{spec.title}: container id does not match invoke.js path")
        return
    if not source_host.endswith("highperformanceformat.com"):
        raise ValueError(f"{spec.title}: unexpected banner script host")
    width = _banner_dimension(code, "width")
    height = _banner_dimension(code, "height")
    if (width, height) != (spec.width, spec.height):
        raise ValueError(
            f"{spec.title}: code dimensions {width}x{height} do not match "
            f"{spec.width}x{spec.height}"
        )
    key_match = re.search(r"['\"]key['\"]\s*:\s*['\"]([a-z0-9]+)['\"]", code, flags=re.I)
    if not key_match or f"/{key_match.group(1)}/invoke.js" not in source:
        raise ValueError(f"{spec.title}: atOptions key does not match invoke.js path")


def normalize_adsterra_config(value: dict[str, Any], *, require_complete: bool = True) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Adsterra config must be a JSON object")
    unknown = sorted(set(value) - ALLOWED_TOP_LEVEL)
    if unknown:
        raise ValueError(f"unknown Adsterra field(s): {', '.join(unknown)}")
    domain_id = str(value.get("domain_id") or "").strip()
    domain_name = _domain(str(value.get("domain_name") or ""))
    game = " ".join(str(value.get("game") or "").split())
    if not domain_id or not domain_id.isdigit():
        raise ValueError("domain_id must be a numeric string")
    if not domain_name or "." not in domain_name:
        raise ValueError("domain_name must be a valid hostname")
    raw_placements = value.get("placements")
    if not isinstance(raw_placements, list):
        raise ValueError("placements must be an array")
    normalized: dict[str, dict[str, str]] = {}
    placement_ids: set[str] = set()
    for raw in raw_placements:
        if not isinstance(raw, dict):
            raise ValueError("every placement must be an object")
        unknown_placement = sorted(set(raw) - ALLOWED_PLACEMENT_FIELDS)
        if unknown_placement:
            raise ValueError(f"unknown placement field(s): {', '.join(unknown_placement)}")
        title = str(raw.get("title") or "").strip()
        if title not in PLACEMENT_BY_TITLE:
            raise ValueError(f"unsupported or misspelled placement title: {title!r}")
        if title in normalized:
            raise ValueError(f"duplicate placement title: {title}")
        placement_id = str(raw.get("placement_id") or "").strip()
        alias = str(raw.get("alias") or "").strip()
        code = str(raw.get("code") or "").strip()
        if not placement_id.isdigit() or placement_id in placement_ids:
            raise ValueError(f"{title}: placement_id must be unique and numeric")
        if not alias:
            raise ValueError(f"{title}: alias is required")
        _validate_snippet(PLACEMENT_BY_TITLE[title], code)
        placement_ids.add(placement_id)
        normalized[title] = {
            "placement_id": placement_id,
            "title": title,
            "alias": alias,
            "code": code,
        }
    missing = [item.title for item in PLACEMENTS if item.title not in normalized]
    if require_complete and missing:
        raise ValueError(f"missing required Adsterra placement(s): {', '.join(missing)}")
    return {
        "schemaVersion": 1,
        "taskType": "ads",
        "game": game,
        "domain_id": domain_id,
        "domain_name": domain_name,
        "placements": [normalized[item.title] for item in PLACEMENTS if item.title in normalized],
    }


def _project_identity(project: Path) -> str:
    path = project / "intake" / "site-identity.json"
    if not path.is_file():
        return ""
    return str(read_json(path).get("GAME_NAME") or "").strip()


def _project_vercel_name(project: Path) -> str:
    linked = project / ".vercel" / "project.json"
    if linked.is_file():
        return str(read_json(linked).get("projectName") or "").strip()
    receipt = project / ".gamewiki" / "publish.json"
    if receipt.is_file():
        return str(((read_json(receipt).get("stages") or {}).get("vercel") or {}).get("projectName") or "").strip()
    return project.name


def resolve_project(config: dict[str, Any], projects_root: Path = PROJECTS_ROOT) -> tuple[Path, str]:
    game = str(config.get("game") or "").strip()
    domain_name = _domain(str(config["domain_name"]))
    candidates: list[Path] = []
    if game:
        direct = (projects_root / slugify(game)).resolve()
        if direct.parent == projects_root.resolve() and direct.is_dir():
            candidates.append(direct)
    domain_stem = domain_name.split(".", 1)[0]
    for suffix in ("-roblox", "-wiki"):
        if domain_stem.endswith(suffix):
            domain_stem = domain_stem[: -len(suffix)]
    direct_domain = (projects_root / domain_stem).resolve()
    if direct_domain.parent == projects_root.resolve() and direct_domain.is_dir() and direct_domain not in candidates:
        candidates.append(direct_domain)
    for linked in projects_root.glob("*/.vercel/project.json"):
        project = linked.parent.parent.resolve()
        if ".pre-full-build-" in project.name:
            continue
        if project not in candidates and (
            _project_vercel_name(project) == domain_stem
            or (game and _compact_identity(_project_identity(project)) == _compact_identity(game))
        ):
            candidates.append(project)
    if game:
        candidates = [
            project for project in candidates
            if _compact_identity(_project_identity(project)) == _compact_identity(game)
        ]
    if len(candidates) != 1:
        raise RuntimeError(
            f"Adsterra target must resolve to exactly one local project; found {len(candidates)} "
            f"for game={game!r}, domain={domain_name!r}"
        )
    return candidates[0], _project_vercel_name(candidates[0])


def _vercel_query(env: dict[str, str]) -> str:
    team_id = env.get("VERCEL_TEAM_ID", "").strip()
    return f"?teamId={urllib.parse.quote(team_id)}" if team_id else ""


def verify_project_domain(project_name: str, domain_name: str, env: dict[str, str]) -> dict[str, Any]:
    token = env.get("VERCEL_TOKEN", "").strip()
    if token:
        query = _vercel_query(env)
        project = _http_json("GET", f"https://api.vercel.com/v9/projects/{urllib.parse.quote(project_name)}{query}", token)
        project_id = str(project.get("id") or project_name)
        separator = "&" if query else "?"
        domains_payload = _http_json(
            "GET",
            f"https://api.vercel.com/v9/projects/{urllib.parse.quote(project_id)}/domains{query}{separator}limit=100",
            token,
        )
        domains = {_domain(str(item.get("name") or "")) for item in domains_payload.get("domains") or []}
        if _domain(domain_name) not in domains:
            raise RuntimeError(
                f"Adsterra domain {_domain(domain_name)!r} is not attached to Vercel project "
                f"{project_name!r}; refusing to configure ads"
            )
        return {"projectId": project_id, "projectName": str(project.get("name") or project_name), "domains": sorted(domains)}

    vercel = shutil.which("vercel.cmd") or shutil.which("vercel")
    if not vercel:
        raise RuntimeError("VERCEL_TOKEN or an authenticated Vercel CLI is required")
    result = subprocess.run(
        [vercel, "domains", "inspect", _domain(domain_name), "--no-color"],
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    output = result.stdout + "\n" + result.stderr
    if result.returncode:
        raise RuntimeError(output.strip())
    relation = re.compile(
        rf"(?m)^\s*{re.escape(project_name)}\s+{re.escape(_domain(domain_name))}\s*$",
        flags=re.I,
    )
    if not relation.search(output):
        raise RuntimeError(
            f"Adsterra domain {_domain(domain_name)!r} is not attached to Vercel project "
            f"{project_name!r}; refusing to configure ads"
        )
    return {"projectId": project_name, "projectName": project_name, "domains": [_domain(domain_name)]}


def _env_payloads(config: dict[str, Any]) -> list[tuple[PlacementSpec, str, str]]:
    by_title = {str(item["title"]): item for item in config["placements"]}
    result = []
    for spec in PLACEMENTS:
        raw = by_title.get(spec.title)
        if not raw:
            continue
        code = str(raw["code"])
        encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
        rendered = re.sub(
            r"(<script\b[^>]*\bsrc=['\"])//",
            r"\1https://",
            code,
            flags=re.I,
        )
        result.append((spec, encoded, hashlib.sha256(rendered.encode("utf-8")).hexdigest()))
    return result


def configure_vercel_ads(config: dict[str, Any], project: Path, project_name: str, env: dict[str, str]) -> dict[str, Any]:
    token = env.get("VERCEL_TOKEN", "").strip()
    verified = verify_project_domain(project_name, str(config["domain_name"]), env)
    if token:
        query = _vercel_query(env)
        separator = "&" if query else "?"
        for spec, encoded, _digest in _env_payloads(config):
            _http_json(
                "POST",
                f"https://api.vercel.com/v10/projects/{urllib.parse.quote(verified['projectId'])}/env{query}{separator}upsert=true",
                token,
                {
                    "key": spec.env_name,
                    "value": encoded,
                    "type": "encrypted",
                    "target": ["production"],
                },
            )
    else:
        vercel = shutil.which("vercel.cmd") or shutil.which("vercel")
        if not vercel:
            raise RuntimeError("authenticated Vercel CLI is required")
        link = subprocess.run(
            [vercel, "link", "--yes", "--project", verified["projectName"], "--no-color"],
            cwd=project,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        if link.returncode:
            raise RuntimeError((link.stderr or link.stdout).strip())
        for spec, encoded, _digest in _env_payloads(config):
            # Stdin keeps ad code and its Base64 transport out of argv/process lists.
            result = subprocess.run(
                [vercel, "env", "add", spec.env_name, "production", "--force", "--yes", "--sensitive", "--no-color"],
                cwd=project,
                env=env,
                input=encoded + "\n",
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
            )
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout).strip())
    deployment_url = _deploy_with_vercel_cli(project, verified["projectName"], env)
    return {**verified, "deploymentUrl": deployment_url}


def verify_deployment_ads(deployment_url: str, config: dict[str, Any], attempts: int = 12) -> dict[str, Any]:
    origins = list(dict.fromkeys([
        deployment_url.rstrip("/"),
        f"https://{_domain(str(config['domain_name']))}",
    ]))
    if not any(origin.startswith("http") for origin in origins):
        raise RuntimeError("Vercel deployment did not return a verification URL")
    expected = {spec.route_format: raw for spec, _encoded, raw in _env_payloads(config)}
    pending = set(expected)
    last_errors: dict[str, str] = {}
    for attempt in range(attempts):
        for route_format in list(pending):
            errors = []
            for origin in origins:
                try:
                    with urllib.request.urlopen(f"{origin}/api/ads/{route_format}", timeout=30) as response:
                        body = response.read().decode("utf-8", errors="replace")
                    if response.status == 200 and hashlib.sha256(
                        _extract_injected_snippet(body).encode("utf-8")
                    ).hexdigest() == expected[route_format]:
                        pending.remove(route_format)
                        last_errors.pop(route_format, None)
                        break
                    errors.append(f"{origin}: HTTP {response.status} or snippet hash mismatch")
                except Exception as exc:  # deployment propagation may briefly return 404/5xx
                    errors.append(f"{origin}: {exc}")
            if route_format in pending:
                last_errors[route_format] = "; ".join(errors)
        if not pending:
            return {"status": "verified", "routes": sorted(expected), "checkedAt": _now()}
        if attempt + 1 < attempts:
            time.sleep(5)
    raise RuntimeError(f"Ad routes did not verify after deployment: {last_errors}")


def _extract_injected_snippet(document: str) -> str:
    match = re.search(r"<!--gamewiki-ad-start-->(.*?)<!--gamewiki-ad-end-->", document, flags=re.S)
    return match.group(1).strip() if match else ""


def import_ads(config_path: Path, *, no_deploy: bool = False) -> dict[str, Any]:
    source = read_json(config_path.expanduser().resolve())
    config = normalize_adsterra_config(source)
    project, project_name = resolve_project(config)
    env = build_subprocess_env(ROOT)
    result = configure_vercel_ads(config, project, project_name, env)
    verification = {"status": "skipped"} if no_deploy else verify_deployment_ads(result["deploymentUrl"], config)
    receipt = {
        "schemaVersion": 1,
        "game": _project_identity(project),
        "domainId": config["domain_id"],
        "domainName": config["domain_name"],
        "vercelProject": result["projectName"],
        "deploymentUrl": result["deploymentUrl"],
        "placements": [
            {
                "placementId": raw["placement_id"],
                "title": spec.title,
                "environmentVariable": spec.env_name,
                "sha256": digest,
            }
            for (spec, _encoded, digest), raw in zip(_env_payloads(config), config["placements"], strict=True)
        ],
        "verification": verification,
        "updatedAt": _now(),
    }
    write_json(project / ".gamewiki" / "ads.json", receipt)
    return receipt


def ads_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gamewiki.py ads")
    subparsers = parser.add_subparsers(dest="command", required=True)
    importer = subparsers.add_parser("import", help="Validate Adsterra JSON, configure Vercel, and redeploy")
    importer.add_argument("--config", type=Path, required=True)
    importer.add_argument("--no-verify", action="store_true", help="Skip post-deployment route verification")
    args = parser.parse_args(argv)
    if args.command == "import":
        receipt = import_ads(args.config, no_deploy=args.no_verify)
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0
    return 2
