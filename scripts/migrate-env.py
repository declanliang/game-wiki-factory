"""Merge legacy pipeline .env files into the ignored factory-root .env."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orchestrate_wiki import parse_dotenv


LEGACY = [
    ROOT / "pipeline" / "basic-info" / ".env",
    ROOT / "pipeline" / "guide-search" / ".env",
    ROOT / "pipeline" / "seo-scout" / ".env",
]
ALIASES = {
    "TOAPIS_API_KEY": ("TOAPIS_API_KEY", "toapis_API_KEY", "toapis_api_key", "TOAPIS_KEY", "toapis_key"),
    "PERPLEXITY_API_KEY": ("PERPLEXITY_API_KEY", "perplexity_api_key"),
    "DATAFORSEO_LOGIN": ("DATAFORSEO_LOGIN", "dataforseo_name"),
    "DATAFORSEO_PASSWORD": ("DATAFORSEO_PASSWORD", "dataforseo_password"),
}


def main() -> int:
    sources = [parse_dotenv(ROOT / ".env"), *[parse_dotenv(path) for path in LEGACY]]
    merged: dict[str, str] = {}
    for source in sources:
        for key, value in source.items():
            merged.setdefault(key, value)
    for canonical, names in ALIASES.items():
        for source in sources:
            value = next((source[name] for name in names if source.get(name, "").strip()), "")
            if value:
                merged[canonical] = value
                break
    legacy_aliases = {name for names in ALIASES.values() for name in names} - set(ALIASES)
    for name in legacy_aliases:
        merged.pop(name, None)
    temporary = ROOT / ".env.migrating"
    lines = ["# Private factory configuration. Never commit or share this file.", ""]
    lines.extend(f"{key}={value}" for key, value in merged.items())
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temporary, ROOT / ".env")
    for path in LEGACY:
        path.unlink(missing_ok=True)
    print(f"Migrated {len(merged)} environment keys to {ROOT / '.env'}")
    print("Removed legacy pipeline .env files; no secret values were printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
