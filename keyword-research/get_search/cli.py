from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import Settings
from .llm_cluster import DEFAULT_CLUSTER_MODEL, DEFAULT_CONTEXT_MODEL
from .pipeline import run_pipeline


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Collect and classify Roblox game keywords.")
    result.add_argument("topic", nargs="?", help="Game topic, for example: animal hospital roblox")
    result.add_argument("--location", default="United States")
    result.add_argument("--language", default="en")
    result.add_argument("--labs-limit", type=int, default=200)
    result.add_argument("--youtube-depth", type=int, default=100)
    result.add_argument(
        "--autocomplete-prefixes",
        choices=("az", "none"),
        default="az",
        help="Use main query plus a-z, or only the main query.",
    )
    result.add_argument(
        "--suggest-source",
        choices=("auto", "google", "dataforseo", "manual"),
        default="auto",
        help=(
            "auto always uses direct Google Suggest; "
            "manual requires that file."
        ),
    )
    result.add_argument("--from-run", type=Path, help="Rebuild classification from an existing run.")
    result.add_argument(
        "--refresh-source",
        action="append",
        choices=("labs", "trends", "autocomplete", "youtube"),
        default=[],
        help="With --from-run, recollect only this source. May be repeated.",
    )
    result.add_argument(
        "--cluster-mode",
        choices=("llm", "rules"),
        default="llm",
        help="Use web-informed ToAPIs clustering (default), or legacy rules.",
    )
    result.add_argument("--context-model", default=DEFAULT_CONTEXT_MODEL)
    result.add_argument("--cluster-model", default=DEFAULT_CLUSTER_MODEL)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    if args.from_run:
        settings = None
        if args.refresh_source or args.cluster_mode == "llm":
            settings = Settings.from_env(
                root,
                location=args.location,
                language=args.language,
                labs_limit=args.labs_limit,
                youtube_depth=args.youtube_depth,
                suggest_source=args.suggest_source,
            )
        run_dir = run_pipeline(
            root,
            None,
            settings,
            include_az=args.autocomplete_prefixes == "az",
            from_run=args.from_run.resolve(),
            refresh=set(args.refresh_source),
            cluster_mode=args.cluster_mode,
            context_model=args.context_model,
            cluster_model=args.cluster_model,
        )
    else:
        if not args.topic:
            parser().error("topic is required unless --from-run is used")
        if not 1 <= args.labs_limit <= 1000:
            parser().error("--labs-limit must be between 1 and 1000")
        if not 1 <= args.youtube_depth <= 700:
            parser().error("--youtube-depth must be between 1 and 700")
        settings = Settings.from_env(
            root,
            location=args.location,
            language=args.language,
            labs_limit=args.labs_limit,
            youtube_depth=args.youtube_depth,
            suggest_source=args.suggest_source,
        )
        run_dir = run_pipeline(
            root,
            args.topic,
            settings,
            include_az=args.autocomplete_prefixes == "az",
            cluster_mode=args.cluster_mode,
            context_model=args.context_model,
            cluster_model=args.cluster_model,
        )
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    print(f"Output: {run_dir}")
    print(f"DataForSEO: ${manifest['total_cost_usd']:.6f}")
    print(f"ToAPIs tokens: {manifest.get('toapis', {}).get('total_tokens', 0)}")
    print(f"Sources: {json.dumps(manifest['source_counts'], ensure_ascii=False)}")
    return 0
