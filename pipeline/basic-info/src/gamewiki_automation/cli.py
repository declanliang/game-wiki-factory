from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Settings
from .pipeline import Pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate validated Roblox or Steam wiki homepage data from game names.")
    parser.add_argument("games", nargs="+", help="One or more game names; quote names containing spaces.")
    parser.add_argument("--platform", choices=["auto", "roblox", "steam"], default="auto")
    parser.add_argument("--official-url", help="Optional supported-platform URL used for deterministic identity selection.")
    parser.add_argument("--refresh", action="store_true", help="Ignore HTTP and LLM caches.")
    parser.add_argument("--output-dir", type=Path, help="Override GAMEWIKI_OUTPUT_DIR.")
    parser.add_argument("--model", help="Override TOAPIS_MODEL for non-web generation.")
    parser.add_argument("--web-model", help="Override TOAPIS_WEB_MODEL for Responses API web-search tasks.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.load(refresh=args.refresh)
    if args.output_dir:
        settings.output_dir = args.output_dir.resolve()
    if args.model:
        settings.toapis_model = args.model
    if args.web_model:
        settings.toapis_web_model = args.web_model
    failures = 0
    for game in args.games:
        print(f"[start] {game}", flush=True)
        try:
            output_dir, validation = Pipeline(settings).run(
                game, platform=args.platform, official_url=args.official_url
            )
            print(f"[{validation['status']}] {game} -> {output_dir}", flush=True)
            if validation["status"] == "fail":
                failures += 1
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            failures += 1
            print(f"[error] {game}: {exc}", file=sys.stderr, flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
