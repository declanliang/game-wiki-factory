from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from project_contract import (
    FIXED_LANGUAGES,
    build_game_profile,
    build_seo_keywords,
    build_site_plan,
    reconcile_site_plan,
    render_project_readme,
)
from permit_client import shared_permit


ROOT = Path(__file__).resolve().parent
FAVICON_FILES = {
    "favicon.ico",
    "favicon-16x16.png",
    "favicon-32x32.png",
    "apple-touch-icon.png",
    "android-chrome-192x192.png",
    "android-chrome-512x512.png",
    "site.webmanifest",
}
MINIMUM_WIKI_CATEGORIES = 1


class PipelineError(RuntimeError):
    """An expected, user-actionable pipeline failure."""


def slugify(value: str) -> str:
    parts = re.findall(r"[a-z0-9]+", value.casefold())
    if not parts:
        raise PipelineError("The game name must contain at least one letter or number.")
    return "-".join(parts)


def seo_project_name(game_name: str) -> str:
    return game_name.replace(" ", "_").lower()


def keyword_topic(game_name: str, platform: str = "Roblox") -> str:
    """Add the verified platform as search-time disambiguation context."""
    platform_name = platform.strip().title()
    return game_name if platform_name.casefold() in game_name.casefold().split() else f"{game_name} {platform_name}"


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"Required file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Expected a JSON object in {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def parse_dotenv(path: Path) -> dict[str, str]:
    """Read a small .env file without mutating os.environ or logging values."""
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        result[key] = value
    return result


def build_subprocess_env(
    root: Path,
    *,
    extra_env_files: Iterable[Path] = (),
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build one private child environment from canonical and legacy .env files."""
    env = dict(base_env if base_env is not None else os.environ)
    parent = root.parent
    candidates = [
        root / ".env",
        root / "pipeline" / "basic-info" / ".env",
        root / "pipeline" / "guide-search" / ".env",
        root / "pipeline" / "seo-scout" / ".env",
        # Pre-factory paths remain readable during a one-time local migration.
        root / "auto-basic-info" / ".env",
        root / "keyword-research" / ".env",
        root / "seo-scout" / ".env",
        parent / "auto-basic-info" / ".env",
        parent / "get-search" / ".env",
        parent / "seoscout" / ".env",
        *extra_env_files,
    ]
    loaded: dict[str, str] = {}
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        for key, value in parse_dotenv(resolved).items():
            loaded.setdefault(key, value)

    for key, value in loaded.items():
        env.setdefault(key, value)

    def first(*names: str) -> str | None:
        for name in names:
            value = env.get(name, "").strip()
            if value:
                return value
        return None

    aliases = {
        "TOAPIS_API_KEY": first(
            "TOAPIS_API_KEY", "toapis_API_KEY", "toapis_api_key", "TOAPIS_KEY", "toapis_key"
        ),
        "TOAPIS_KEY": first(
            "TOAPIS_KEY", "toapis_key", "TOAPIS_API_KEY", "toapis_API_KEY", "toapis_api_key"
        ),
        "PERPLEXITY_API_KEY": first("PERPLEXITY_API_KEY", "perplexity_api_key"),
        "dataforseo_name": first("dataforseo_name", "DATAFORSEO_LOGIN"),
        "dataforseo_password": first("dataforseo_password", "DATAFORSEO_PASSWORD"),
        "DATAFORSEO_LOGIN": first("DATAFORSEO_LOGIN", "dataforseo_name"),
        "DATAFORSEO_PASSWORD": first("DATAFORSEO_PASSWORD", "dataforseo_password"),
        "LLM_API_KEY": first(
            "LLM_API_KEY", "LLM_API_KEY_1", "TOAPIS_API_KEY", "toapis_API_KEY", "toapis_key"
        ),
    }
    for key, value in aliases.items():
        if value:
            env[key] = value

    # Numbered factory keys feed SEO Scout's rotation pool. Numbering may have
    # gaps; Config discovers the complete environment instead of stopping at one.
    if env.get("LLM_API_KEY", "").strip():
        if not env.get("LLM_API_KEY_1", "").strip():
            env["LLM_API_KEY_1"] = env["LLM_API_KEY"]
    for name, value in list(env.items()):
        match = re.fullmatch(r"TOAPIS_API_KEY_(\d+)", name)
        if match and value.strip():
            target = f"LLM_API_KEY_{match.group(1)}"
            if not env.get(target, "").strip():
                env[target] = value

    # Child CLIs print multilingual text and emoji. Windows otherwise defaults
    # redirected Python stdout to GBK, which can fail before the first API call.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")

    return env


def run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
    run_log_path: Path,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    display = subprocess.list2cmdline(command)
    header = (
        f"\n[{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}]"
        f"\n[run] {display}\n[cwd] {cwd}\n"
    )
    print(header, end="", flush=True)
    with (
        log_path.open("a", encoding="utf-8") as log,
        run_log_path.open("a", encoding="utf-8") as run_log,
    ):
        log.write(header)
        run_log.write(header)
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        forward_console = True
        try:
            for line in process.stdout:
                log.write(line)
                run_log.write(line)
                log.flush()
                run_log.flush()
                if forward_console:
                    try:
                        sys.stdout.write(line)
                        sys.stdout.flush()
                    except (OSError, ValueError, UnicodeError):
                        # A closed/legacy parent console must never abort paid work;
                        # the dedicated UTF-8 logs remain authoritative.
                        forward_console = False
        finally:
            process.stdout.close()
        return_code = process.wait()
        footer = f"[exit] {return_code}\n"
        log.write(footer)
        run_log.write(footer)
    if return_code:
        raise PipelineError(
            f"Command failed with exit code {return_code}: {display}. See {log_path}"
        )


def validate_basic_output(path: Path) -> tuple[Path, dict, list[str]]:
    output_dir = path.resolve()
    intake = (
        output_dir / "template-intake"
        if (output_dir / "template-intake" / "site-identity.json").is_file()
        else output_dir
    )
    identity = read_json(intake / "site-identity.json")
    languages = identity.get("LANGUAGES")
    if not isinstance(languages, list) or not languages or "en" not in languages:
        raise PipelineError("site-identity.json must declare LANGUAGES including en.")
    normalized_languages = [item.strip() for item in languages if isinstance(item, str) and item.strip()]
    if len(normalized_languages) != len(languages) or len(set(normalized_languages)) != len(normalized_languages):
        raise PipelineError("LANGUAGES must contain unique, non-empty language codes.")
    if normalized_languages != FIXED_LANGUAGES:
        raise PipelineError(
            f"LANGUAGES must match the fixed product policy {FIXED_LANGUAGES}; "
            f"found {normalized_languages}."
        )

    required = {"site-identity.json", "site-content.json"}
    required.update(f"site-content.{locale}.json" for locale in normalized_languages if locale != "en")
    missing = sorted(name for name in required if not (intake / name).is_file())
    heroes = [item for item in intake.glob("hero.*") if item.is_file()]
    if len(heroes) != 1:
        raise PipelineError(f"Expected exactly one hero.<ext> in {intake}; found {len(heroes)}.")
    missing_favicons = sorted(name for name in FAVICON_FILES if not (intake / "favicon" / name).is_file())
    if missing or missing_favicons:
        details = []
        if missing:
            details.append("missing files: " + ", ".join(missing))
        if missing_favicons:
            details.append("missing favicon files: " + ", ".join(missing_favicons))
        raise PipelineError(f"Incomplete template intake at {intake}: {'; '.join(details)}")

    report_path = output_dir / "template-validation-report.json"
    if report_path.is_file():
        report = read_json(report_path)
        if report.get("status") != "pass":
            raise PipelineError(f"Template contract did not pass: {report_path}")
    return intake, identity, normalized_languages


def build_trusted_keyword_context(intake: Path, identity: dict) -> dict:
    """Expose verified upstream game facts to keyword disambiguation and clustering."""
    site_content = read_json(intake / "site-content.json")
    platforms = site_content.get("site", {}).get("gamePlatform") or []
    platform = platforms[0] if platforms else "Game"
    return {
        "source": "auto-basic-info",
        "evidence_policy": (
            f"Treat this {platform} identity and site content as trusted same-game evidence. "
            "It may support unofficial guide topics even when external search demand is sparse."
        ),
        "identity": {
            "game_name": identity.get("GAME_NAME"),
            "official_game_url": identity.get("OFFICIAL_GAME_URL"),
            "platform": platform,
        },
        "site_content": site_content,
    }


def bridge_keywords(raw_keywords: dict, identity: dict, platform: str = "Roblox") -> dict:
    categories = raw_keywords.get("categories")
    if not isinstance(categories, list) or not categories:
        raise PipelineError("get-search keywords.json has no categories.")
    normalized_categories = []
    for index, item in enumerate(categories):
        if not isinstance(item, dict):
            raise PipelineError(f"keywords category #{index + 1} is not an object.")
        category = item.get("category")
        keywords = item.get("keywords")
        if not isinstance(category, str) or not category.strip():
            raise PipelineError(f"keywords category #{index + 1} has no name.")
        if not isinstance(keywords, list) or not keywords or not all(isinstance(k, str) and k.strip() for k in keywords):
            raise PipelineError(f"keywords category {category!r} has no usable keywords.")
        normalized_categories.append(
            {"category": category.strip(), "keywords": [keyword.strip() for keyword in keywords]}
        )
    if len(normalized_categories) < MINIMUM_WIKI_CATEGORIES:
        raise PipelineError(
            "A game guide site requires at least "
            f"{MINIMUM_WIKI_CATEGORIES} useful keyword categories; "
            f"get-search returned {len(normalized_categories)}."
        )

    game_name = str(identity.get("GAME_NAME", "")).strip()
    if not game_name:
        raise PipelineError("site-identity.json has no GAME_NAME.")
    languages = [
        locale
        for locale in identity.get("LANGUAGES", [])
        if isinstance(locale, str) and locale and locale != "en"
    ]
    return {
        "game_name": game_name,
        "filter_keyword": f"{platform} {game_name}",
        "languages": languages,
        "categories": normalized_categories,
    }


def validate_articles(articles_dir: Path, languages: list[str]) -> dict[str, int]:
    if not articles_dir.is_dir():
        raise PipelineError(f"Articles directory does not exist: {articles_dir}")
    by_locale: dict[str, set[Path]] = {}
    for locale in languages:
        locale_dir = articles_dir / locale
        files = {
            path.relative_to(locale_dir)
            for path in locale_dir.rglob("*.mdx")
            if path.is_file()
        } if locale_dir.is_dir() else set()
        if not files:
            raise PipelineError(f"No MDX articles found for declared language {locale}: {locale_dir}")
        by_locale[locale] = files

    english = by_locale["en"]
    for locale, files in by_locale.items():
        if locale == "en":
            continue
        missing = sorted(str(path) for path in english - files)
        extra = sorted(str(path) for path in files - english)
        if missing or extra:
            raise PipelineError(
                f"Article tree for {locale} does not match en. "
                f"Missing: {missing or 'none'}; extra: {extra or 'none'}"
            )
    return {locale: len(files) for locale, files in by_locale.items()}


def reconcile_homepage_guide_links(intake_dir: Path, site_plan: dict) -> None:
    """Resolve Basic Info guide hints only against published site-plan categories."""
    published = {
        str(item.get("id"))
        for item in site_plan.get("categories", [])
        if item.get("status") == "published" and item.get("id")
    }
    for content_path in sorted(intake_dir.glob("site-content*.json")):
        content = read_json(content_path)
        sections = content.get("home", {}).get("guideSections")
        if not isinstance(sections, list):
            continue
        for section in sections:
            for item in section.get("items", []) if isinstance(section, dict) else []:
                if not isinstance(item, dict):
                    continue
                category = item.get("category")
                if category in published:
                    item["href"] = f"/{category}"
                else:
                    item.pop("category", None)
                    item.pop("href", None)
        write_json(content_path, content)


def _video_title_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", value.casefold()):
        if token in {"roblox", "the", "a", "an", "game", "plays", "play"}:
            continue
        if token.endswith("s") and len(token) > 4:
            token = token[:-1]
        tokens.add(token)
    return tokens


def select_featured_youtube_video(raw: dict, game_name: str, platform: str = "Roblox") -> dict | None:
    """Pick one exact-game, long-form video from the cached Guide Search response."""
    game_tokens = _video_title_tokens(game_name)
    if not game_tokens:
        return None
    candidates: list[dict] = []
    tasks = raw.get("response", {}).get("tasks", [])
    for task in tasks if isinstance(tasks, list) else []:
        for result in task.get("result", []) if isinstance(task, dict) else []:
            for item in result.get("items", []) if isinstance(result, dict) else []:
                if not isinstance(item, dict) or item.get("type") != "youtube_video":
                    continue
                video_id = str(item.get("video_id") or "").strip()
                title = str(item.get("title") or "").strip()
                duration = item.get("duration_time_seconds")
                if (
                    not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id)
                    or item.get("is_shorts")
                    or item.get("is_live")
                    or not isinstance(duration, int)
                    or not 120 <= duration <= 3600
                ):
                    continue
                title_tokens = _video_title_tokens(title)
                if not game_tokens.issubset(title_tokens):
                    continue
                title_and_description = f"{title} {item.get('description') or ''}".casefold()
                if platform.casefold() == "roblox" and "roblox" not in title_and_description:
                    continue
                candidates.append(item)
    if not candidates:
        return None
    selected = min(
        candidates,
        key=lambda item: (
            int(item.get("rank_absolute") or 1_000_000),
            -int(item.get("views_count") or 0),
        ),
    )
    return {
        "videoId": selected["video_id"],
        "title": selected.get("title") or "",
        "channelName": selected.get("channel_name") or "",
        "channelUrl": selected.get("channel_url") or "",
        "url": selected.get("url") or f"https://www.youtube.com/watch?v={selected['video_id']}",
        "durationSeconds": selected.get("duration_time_seconds"),
        "source": "guide-search/raw/youtube.json",
        "selectionReason": f"Top-ranked long-form result whose title contains the complete normalized game name and matches the {platform} identity.",
    }


def reconcile_featured_video(intake_dir: Path, keyword_run_dir: Path, planning_dir: Path, platform: str = "Roblox") -> dict | None:
    """Fill an empty homepage video slot from already-paid, cached YouTube research."""
    identity_path = intake_dir / "site-identity.json"
    identity = read_json(identity_path)
    existing = str(identity.get("YOUTUBE_VIDEO_ID") or "").strip()
    if existing:
        selection = {
            "videoId": existing,
            "source": "basic-info/site-identity.json",
            "selectionReason": "Basic Info supplied a verified trailer or introduction video.",
        }
    else:
        youtube_path = keyword_run_dir / "raw" / "youtube.json"
        if not youtube_path.is_file():
            return None
        selection = select_featured_youtube_video(read_json(youtube_path), str(identity.get("GAME_NAME") or ""), platform)
        if not selection:
            return None
        identity["YOUTUBE_VIDEO_ID"] = selection["videoId"]
        write_json(identity_path, identity)
    write_json(planning_dir / "featured-video.json", selection)
    return selection


def latest_keyword_file(search_roots: Iterable[Path], slug: str) -> Path | None:
    matches: list[Path] = []
    for root in search_roots:
        output = root / "output"
        if not output.is_dir():
            continue
        matches.extend(
            path / "keywords.json"
            for path in output.glob(f"{slug}-*")
            if (path / "keywords.json").is_file()
        )
    return max(matches, key=lambda path: path.stat().st_mtime_ns) if matches else None


def latest_keyword_run(search_roots: Iterable[Path], slug: str) -> Path | None:
    required_raw = {"labs.json", "trends.json", "autocomplete.json", "youtube.json"}
    matches: list[Path] = []
    for root in search_roots:
        output = root / "output"
        if not output.is_dir():
            continue
        for path in output.glob(f"{slug}-*"):
            raw_dir = path / "raw"
            if path.is_dir() and raw_dir.is_dir() and required_raw.issubset(
                {item.name for item in raw_dir.iterdir() if item.is_file()}
            ):
                matches.append(path)
    return max(matches, key=lambda path: path.stat().st_mtime_ns) if matches else None


def find_basic_output(search_roots: Iterable[Path], slug: str) -> Path | None:
    for root in search_roots:
        candidate = root / "output" / slug
        if (candidate / "template-intake" / "site-identity.json").is_file():
            return candidate
    return None


def copy_template(template_dir: Path, site_dir: Path) -> None:
    if not template_dir.is_dir():
        raise PipelineError(f"Wiki template directory does not exist: {template_dir}")
    if site_dir.exists():
        raise PipelineError(f"Generated site already exists: {site_dir}")

    excluded_names = {".git", ".next", "node_modules", "intake"}

    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = {name for name in names if name in excluded_names}
        for name in names:
            if name in {".env", ".env.local", "new-site.env"}:
                ignored.add(name)
        return ignored

    shutil.copytree(template_dir, site_dir, ignore=ignore)


def sync_template_source(template_dir: Path, site_dir: Path) -> None:
    """Refresh template code in an existing project without touching runtime data."""
    excluded_names = {".git", ".next", "node_modules", "intake", "content"}
    for item in template_dir.iterdir():
        if item.name in excluded_names or item.name in {".env", ".env.local", "new-site.env"}:
            continue
        target = site_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def copy_directory_contents(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise PipelineError(f"Source directory does not exist: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def replace_directory(source: Path, destination: Path) -> None:
    """Materialize a checkpoint exactly, removing only the known destination."""
    if not source.is_dir():
        raise PipelineError(f"Source directory does not exist: {source}")
    if source.resolve() == destination.resolve():
        return
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run homepage research, keyword research, article generation, and Wiki site assembly."
    )
    parser.add_argument("game", help='Roblox or Steam game name, for example "Funnel Runners"')
    parser.add_argument("--platform", choices=["auto", "roblox", "steam"], default="auto")
    parser.add_argument("--official-url", help="Optional Roblox game or Steam app URL for deterministic identity selection.")
    parser.add_argument("--template-dir", type=Path, default=ROOT / "template")
    parser.add_argument("--seo-scout-dir", type=Path, default=ROOT / "pipeline" / "seo-scout")
    parser.add_argument(
        "--output-root",
        "--projects-dir",
        dest="output_root",
        type=Path,
        default=ROOT.parent,
        help="Parent directory for deployable per-game repositories (default: the factory's parent).",
    )
    parser.add_argument("--runs-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--run-dir", type=Path, help="Compatibility alias for an exact project directory.")
    parser.add_argument("--resume", action="store_true", help="Resume is automatic; retained for explicitness and compatibility.")
    parser.add_argument("--env-file", type=Path, action="append", default=[], help="Additional private .env file.")
    parser.add_argument("--basic-output", type=Path, help="Existing basic-info game output or template-intake directory.")
    parser.add_argument("--keywords-file", type=Path, help="Existing get-search keywords.json.")
    parser.add_argument("--articles-dir", type=Path, help="Existing articles directory containing en/, es/, etc.")
    parser.add_argument("--skip-basic", action="store_true", help="Reuse --basic-output or the latest local output.")
    parser.add_argument("--skip-keywords", action="store_true", help="Reuse --keywords-file or the latest local output.")
    parser.add_argument(
        "--recluster-keywords",
        action="store_true",
        help="Reuse an existing run's raw sources but rebuild candidates and LLM clustering.",
    )
    parser.add_argument("--skip-articles", action="store_true", help="Reuse --articles-dir or an existing seo-scout project.")
    parser.add_argument("--skip-site", action="store_true", help="Prepare the complete intake package but do not create/build a site.")
    parser.add_argument("--skip-build", action="store_true", help="Run template ingestion and checks without the Next.js production build.")
    parser.add_argument("--publish", action="store_true", help="Publish a verified site to GitHub and Vercel after generation.")
    parser.add_argument("--refresh-basic", action="store_true", help="Ignore auto-basic-info caches (may incur API cost).")
    parser.add_argument("--overwrite-articles", action="store_true", help="Regenerate existing seo-scout articles (may incur API cost).")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    started = datetime.now(timezone.utc)
    slug = slugify(args.game)
    search_topic = args.game
    search_slug = slugify(search_topic)
    project_dir = (
        args.run_dir.expanduser().resolve()
        if args.run_dir
        else (args.output_root.expanduser().resolve() / slug)
    )
    state_dir = project_dir / ".gamewiki"
    manifest_path = state_dir / "manifest.json"
    is_resume = manifest_path.is_file()
    if project_dir.exists() and not is_resume:
        existing = [item.name for item in project_dir.iterdir()]
        if existing:
            raise PipelineError(
                f"Output directory already exists but is not a Game Wiki project: {project_dir}"
            )
    project_dir.mkdir(parents=True, exist_ok=True)
    attempt_id = started.strftime("%Y%m%dT%H%M%SZ")
    run_log_path = state_dir / "logs" / f"orchestrator-{attempt_id}.log"
    run_log_path.parent.mkdir(parents=True, exist_ok=True)
    with run_log_path.open("w", encoding="utf-8") as run_log:
        run_log.write(
            f"\n=== Game Wiki run started {started.replace(microsecond=0).isoformat()} ===\n"
            f"game={args.game}\nproject={project_dir}\nresume={is_resume}\n"
        )
    latest_pointer = ROOT / ".gamewiki" / "latest-project.txt"
    latest_pointer.parent.mkdir(parents=True, exist_ok=True)
    latest_pointer.write_text(str(project_dir) + "\n", encoding="utf-8")
    print(f"[log] {run_log_path}", flush=True)
    if is_resume and manifest_path.is_file():
        manifest = read_json(manifest_path)
        if manifest.get("slug") != slug:
            raise PipelineError(
                f"Project directory belongs to {manifest.get('game')!r}, not {args.game!r}: {project_dir}"
            )
        manifest["status"] = "running"
        manifest.pop("error", None)
        manifest.pop("finishedAt", None)
    else:
        manifest: dict[str, object] = {
            "version": 3,
            "game": args.game,
            "slug": slug,
            "keywordTopic": search_topic,
            "status": "running",
            "startedAt": started.replace(microsecond=0).isoformat(),
            "stages": {},
            "paths": {"project": str(project_dir)},
        }
    # Loading a v1/v2 checkpoint is also the layout migration boundary.  From
    # this point onward the game root is the deployable site and local factory
    # state lives under .gamewiki/.
    manifest["version"] = 3
    manifest["keywordTopic"] = search_topic
    manifest["currentAttempt"] = {"id": attempt_id, "log": str(run_log_path)}
    paths = manifest.setdefault("paths", {})
    assert isinstance(paths, dict)
    paths["project"] = str(project_dir)
    paths["state"] = str(state_dir)
    paths["intake"] = str(project_dir / "intake")

    def record(stage: str, status: str, **details: object) -> None:
        stages = manifest["stages"]
        assert isinstance(stages, dict)
        stages[stage] = {"status": status, **details}
        write_json(manifest_path, manifest)

    write_json(manifest_path, manifest)
    env = build_subprocess_env(ROOT, extra_env_files=args.env_file)
    python = sys.executable
    basic_dir = ROOT / "pipeline" / "basic-info"
    keywords_dir = ROOT / "pipeline" / "guide-search"
    seo_dir = args.seo_scout_dir.expanduser().resolve()

    try:
        basic_root = state_dir / "basic-info"
        project_basic_output = basic_root / slug
        project_basic_valid = False
        if project_basic_output.is_dir() and not args.refresh_basic:
            try:
                validate_basic_output(project_basic_output)
                project_basic_valid = True
            except PipelineError:
                project_basic_valid = False
        if project_basic_valid:
            basic_output = project_basic_output
            record("basic", "reused", output=str(basic_output), checkpoint="validated")
        elif args.skip_basic:
            basic_output = args.basic_output.expanduser().resolve() if args.basic_output else find_basic_output(
                [basic_dir, ROOT.parent / "auto-basic-info"], slug
            )
            if basic_output is None:
                raise PipelineError("--skip-basic needs --basic-output or an existing local output.")
            record("basic", "reused", output=str(basic_output))
        else:
            command = [
                python, "-m", "gamewiki_automation", args.game,
                "--output-dir", str(basic_root), "--platform", args.platform,
            ]
            if args.official_url:
                command.extend(["--official-url", args.official_url])
            if args.refresh_basic:
                command.append("--refresh")
            basic_env = dict(env)
            basic_env["PYTHONPATH"] = os.pathsep.join(
                filter(None, [str(basic_dir / "src"), basic_env.get("PYTHONPATH", "")])
            )
            # Basic Info normally resolves its cache relative to the source
            # checkout.  Override it with an absolute per-game path so no
            # real-game HTTP/LLM state leaks back into the clean template.
            basic_env["GAMEWIKI_CACHE_DIR"] = str(basic_root / ".cache")
            run_command(
                command,
                cwd=basic_dir,
                env=basic_env,
                log_path=state_dir / "logs" / f"{attempt_id}-basic.log",
                run_log_path=run_log_path,
            )
            basic_output = basic_root / slug
            record("basic", "generated", output=str(basic_output))

        basic_intake, identity, languages = validate_basic_output(basic_output)
        basic_site_content = read_json(basic_intake / "site-content.json")
        platform_values = basic_site_content.get("site", {}).get("gamePlatform") or []
        resolved_platform = str(platform_values[0] if platform_values else "Roblox")
        search_topic = keyword_topic(args.game, resolved_platform)
        search_slug = slugify(search_topic)
        manifest["platform"] = resolved_platform
        manifest["keywordTopic"] = search_topic
        canonical_name = str(identity["GAME_NAME"])
        manifest["canonicalGameName"] = canonical_name
        manifest["languages"] = languages
        planning_dir = state_dir / "planning"
        planning_dir.mkdir(parents=True, exist_ok=True)
        game_profile = build_game_profile(basic_output)
        game_profile_path = planning_dir / "game-profile.json"
        write_json(game_profile_path, game_profile)
        record("gameProfile", "generated", output=str(game_profile_path))
        keyword_context_path = planning_dir / "keyword-context.json"
        write_json(keyword_context_path, build_trusted_keyword_context(basic_intake, identity))
        keyword_context = read_json(keyword_context_path)
        keyword_context["game_profile"] = game_profile
        write_json(keyword_context_path, keyword_context)
        manifest["keywordContext"] = str(keyword_context_path)

        keyword_run_dir = planning_dir / "guide-search"
        project_keyword_file = keyword_run_dir / "keywords.json"
        if args.keywords_file:
            source_keyword_file = args.keywords_file.expanduser().resolve()
            if not source_keyword_file.is_file():
                raise PipelineError(f"Keyword file does not exist: {source_keyword_file}")
            source_run = source_keyword_file.parent
            if source_run != keyword_run_dir:
                replace_directory(source_run, keyword_run_dir)
            keyword_file = project_keyword_file
            record("keywords", "migrated", output=str(keyword_file), source=str(source_run))
        elif project_keyword_file.is_file() and not args.recluster_keywords:
            keyword_file = project_keyword_file
            record("keywords", "reused", output=str(keyword_file), checkpoint="validated")
        elif args.skip_keywords:
            source_keyword_file = latest_keyword_file([keywords_dir, ROOT.parent / "get-search"], search_slug)
            if source_keyword_file is None:
                raise PipelineError("--skip-keywords needs --keywords-file or an existing local output.")
            replace_directory(source_keyword_file.parent, keyword_run_dir)
            keyword_file = project_keyword_file
            record("keywords", "migrated", output=str(keyword_file), source=str(source_keyword_file.parent))
        else:
            reusable_run = keyword_run_dir if (keyword_run_dir / "raw").is_dir() else latest_keyword_run([keywords_dir], search_slug)
            if reusable_run and reusable_run != keyword_run_dir:
                replace_directory(reusable_run, keyword_run_dir)
                reusable_run = keyword_run_dir
            if reusable_run and project_keyword_file.is_file() and not args.recluster_keywords:
                keyword_file = project_keyword_file
                record("keywords", "reused", output=str(keyword_file), checkpoint="migrated")
            else:
                command = [
                    python,
                    "main.py",
                    search_topic,
                    "--trusted-context-file",
                    str(keyword_context_path),
                ]
                if reusable_run:
                    command.extend(["--from-run", str(reusable_run)])
                    record("keywords", "resuming", output=str(reusable_run))
                else:
                    command.extend(["--run-dir", str(keyword_run_dir)])
                run_command(
                    command,
                    cwd=keywords_dir,
                    env=env,
                    log_path=state_dir / "logs" / f"{attempt_id}-guide-search.log",
                    run_log_path=run_log_path,
                )
                keyword_file = project_keyword_file
                if not keyword_file.is_file():
                    raise PipelineError(f"get-search did not produce keywords.json: {keyword_file}")
                record("keywords", "generated", output=str(keyword_file))

        raw_keywords = read_json(keyword_file)
        site_plan = build_site_plan(game_profile, raw_keywords)
        site_plan_path = planning_dir / "site-plan.json"
        write_json(site_plan_path, site_plan)
        bridge_path = planning_dir / "seo-keywords.json"
        write_json(bridge_path, build_seo_keywords(site_plan))
        record("sitePlan", "generated", output=str(site_plan_path))
        record("keywordBridge", "generated", output=str(bridge_path))

        project = seo_project_name(canonical_name)
        content_project_dir = state_dir / "content-pipeline"
        legacy_seo_project = seo_dir / "projects" / project
        if not content_project_dir.exists() and legacy_seo_project.is_dir():
            shutil.copytree(legacy_seo_project, content_project_dir)
            record("contentMigration", "migrated", source=str(legacy_seo_project), output=str(content_project_dir))
        if args.articles_dir:
            supplied_articles = args.articles_dir.expanduser().resolve()
            replace_directory(supplied_articles, content_project_dir / "articles")
            record("articleSeed", "migrated", source=str(supplied_articles), output=str(content_project_dir / "articles"))

        if args.skip_articles:
            articles_dir = content_project_dir / "articles"
            if not articles_dir.is_dir():
                raise PipelineError("--skip-articles needs --articles-dir or a migrated project checkpoint.")
            record("articles", "reused", output=str(articles_dir))
        else:
            if not (seo_dir / "seoscout").is_dir():
                raise PipelineError(f"seo-scout source is missing: {seo_dir}")
            command = [
                python,
                "-m",
                "seoscout",
                "--project-dir",
                str(content_project_dir),
                "run",
                "--keywords",
                str(bridge_path),
            ]
            if args.overwrite_articles:
                command.append("--overwrite")
            record("articles", "running", output=str(content_project_dir / "articles"))
            try:
                run_command(
                    command,
                    cwd=seo_dir,
                    env=env,
                    log_path=state_dir / "logs" / f"{attempt_id}-seo-scout.log",
                    run_log_path=run_log_path,
                )
            except Exception:
                record("articles", "failed", output=str(content_project_dir / "articles"))
                raise
            articles_dir = content_project_dir / "articles"
            record("articles", "generated", output=str(articles_dir))

        article_counts = validate_articles(articles_dir, languages)
        try:
            site_plan = reconcile_site_plan(site_plan, articles_dir)
        except ValueError as exc:
            raise PipelineError(str(exc)) from exc
        write_json(site_plan_path, site_plan)
        record("sitePlan", "reconciled", output=str(site_plan_path), qualityGate=site_plan["qualityGate"])

        intake_dir = project_dir / "intake"
        if intake_dir.exists():
            shutil.rmtree(intake_dir)
        copy_directory_contents(basic_intake, intake_dir)
        shutil.copytree(articles_dir, intake_dir / "articles")
        shutil.copy2(site_plan_path, intake_dir / "site-plan.json")
        featured_video = reconcile_featured_video(intake_dir, keyword_run_dir, planning_dir, resolved_platform)
        record(
            "featuredVideo",
            "selected" if featured_video else "unavailable",
            output=str(planning_dir / "featured-video.json") if featured_video else None,
            source=featured_video.get("source") if featured_video else None,
        )
        reconcile_homepage_guide_links(intake_dir, site_plan)
        record("intake", "prepared", output=str(intake_dir), articles=article_counts)

        if args.skip_site:
            record("site", "skipped")
        else:
            template_dir = args.template_dir.expanduser().resolve()
            site_dir = project_dir
            had_site = (site_dir / "package.json").is_file()
            sync_template_source(template_dir, site_dir)
            record(
                "siteCopy",
                "refreshed" if had_site else "generated",
                output=str(site_dir),
                source=str(template_dir),
            )
            npm = shutil.which("npm.cmd") or shutil.which("npm")
            if not npm:
                raise PipelineError("npm was not found on PATH; Node.js 20–24 is required.")
            if (site_dir / "node_modules").is_dir():
                record("dependencies", "reused", output=str(site_dir / "node_modules"))
            else:
                run_command(
                    [npm, "ci"],
                    cwd=site_dir,
                    env=env,
                    log_path=state_dir / "logs" / f"{attempt_id}-npm-install.log",
                    run_log_path=run_log_path,
                )
                record("dependencies", "installed", output=str(site_dir / "node_modules"))
            launch = [npm, "run", "launch:site"]
            if args.skip_build:
                launch.extend(["--", "--skip-build"])
            with shared_permit("build"):
                run_command(
                    launch,
                    cwd=site_dir,
                    env=env,
                    log_path=state_dir / "logs" / f"{attempt_id}-site.log",
                    run_log_path=run_log_path,
                )
            record("site", "generated", output=str(site_dir), buildSkipped=args.skip_build)
            paths = manifest["paths"]
            assert isinstance(paths, dict)
            paths["site"] = str(site_dir)

        manifest["status"] = "complete"
        manifest["finishedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        write_json(manifest_path, manifest)
        if not args.skip_site:
            (project_dir / "README.md").write_text(
                render_project_readme(canonical_name),
                encoding="utf-8",
            )
        if args.publish:
            if args.skip_site or args.skip_build:
                raise PipelineError("--publish requires a complete site and production build verification.")
            from publisher import publish
            publish([slug, "--project-dir", str(project_dir)])
            record("publish", "complete", output=str(project_dir / ".gamewiki" / "publish.json"))
        with run_log_path.open("a", encoding="utf-8") as run_log:
            run_log.write(
                f"\n[complete] {canonical_name}\n"
                f"finished={manifest['finishedAt']}\n"
                f"manifest={manifest_path}\n"
            )
        print(f"\n[complete] {canonical_name}\nProject: {project_dir}\nIntake: {intake_dir}", flush=True)
        if not args.skip_site:
            print(f"Site: {project_dir}", flush=True)
        return 0
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        manifest["finishedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        write_json(manifest_path, manifest)
        failure_traceback = traceback.format_exc()
        with run_log_path.open("a", encoding="utf-8") as run_log:
            run_log.write(
                f"\n[failed] {exc}\n"
                f"finished={manifest['finishedAt']}\n"
                f"manifest={manifest_path}\n"
                f"\n{failure_traceback}\n"
            )
        if isinstance(exc, PipelineError):
            print(
                f"\n[failed] {exc}\n[log] {run_log_path}\n[manifest] {manifest_path}",
                file=sys.stderr,
                flush=True,
            )
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
