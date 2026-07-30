"""Validated shared Adsterra profile used by Cloudflare Pages provisioning."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_PROFILE_PATH = ROOT / "config" / "ads" / "animal-hospital-profile.json"

AD_ENV_NAMES = (
    "AD_NATIVE_BANNER_B64",
    "AD_NATIVE_BANNER_MOBILE_B64",
    "AD_BANNER_728X90_B64",
    "AD_BANNER_300X250_B64",
    "AD_BANNER_468X60_B64",
    "AD_SIDEBAR_160X600_B64",
    "AD_SIDEBAR_160X300_B64",
    "AD_MOBILE_320X50_B64",
)


def _normalize_snippet(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def load_shared_ad_environment(path: Path = DEFAULT_PROFILE_PATH) -> dict[str, str]:
    """Return validated single-line Base64 values keyed by the fixed env contract."""
    profile = json.loads(path.read_text(encoding="utf-8"))
    placements = profile.get("placements")
    if profile.get("schemaVersion") != 1 or not isinstance(placements, dict):
        raise RuntimeError(f"Invalid shared ad profile schema: {path}")

    encoded: dict[str, str] = {}
    for name, placement in placements.items():
        if not isinstance(placement, dict):
            raise RuntimeError(f"Invalid placement {name!r} in {path}")
        env_name = str(placement.get("env") or "").strip()
        snippet = _normalize_snippet(str(placement.get("snippet") or ""))
        if env_name not in AD_ENV_NAMES or env_name in encoded:
            raise RuntimeError(f"Invalid or duplicate ad environment mapping: {env_name!r}")
        if "<script" not in snippet.casefold() or "invoke.js" not in snippet.casefold():
            raise RuntimeError(f"Placement {name!r} does not contain a complete script snippet")
        if placement.get("format") == "native":
            script_key = re.search(r"/([a-f0-9]{32})/invoke\.js", snippet, re.I)
            container_key = re.search(r'id=["\']container-([a-f0-9]{32})["\']', snippet, re.I)
            if not script_key or not container_key or script_key.group(1).casefold() != container_key.group(1).casefold():
                raise RuntimeError(f"Native placement {name!r} has mismatched script/container IDs")
        else:
            width = int(placement.get("width") or 0)
            height = int(placement.get("height") or 0)
            if not re.search(rf"['\"]width['\"]\s*:\s*{width}\b", snippet):
                raise RuntimeError(f"Banner placement {name!r} width does not match its profile")
            if not re.search(rf"['\"]height['\"]\s*:\s*{height}\b", snippet):
                raise RuntimeError(f"Banner placement {name!r} height does not match its profile")
        value = base64.b64encode(snippet.encode("utf-8")).decode("ascii")
        if base64.b64decode(value).decode("utf-8") != snippet or "\n" in value:
            raise RuntimeError(f"Base64 round-trip failed for placement {name!r}")
        encoded[env_name] = value

    missing = sorted(set(AD_ENV_NAMES) - set(encoded))
    extra = sorted(set(encoded) - set(AD_ENV_NAMES))
    if missing or extra:
        raise RuntimeError(f"Shared ad profile must define exactly 8 variables; missing={missing}, extra={extra}")
    return {name: encoded[name] for name in AD_ENV_NAMES}
