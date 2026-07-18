from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path) -> None:
    """Load a minimal .env file without overwriting existing environment values."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    api_login: str
    api_password: str
    toapis_api_key: str | None = None
    location: str = "United States"
    language: str = "en"
    labs_limit: int = 200
    youtube_depth: int = 100
    suggest_source: str = "auto"
    timeout_seconds: int = 120

    @classmethod
    def from_env(cls, root: Path, **overrides: object) -> "Settings":
        load_dotenv(root / ".env")
        login = os.getenv("dataforseo_name", "").strip()
        password = os.getenv("dataforseo_password", "").strip()
        if not login or not password:
            raise ValueError(
                "Missing DataForSEO credentials. Configure dataforseo_name and "
                "dataforseo_password in .env."
            )
        toapis_key = next(
            (
                os.getenv(name, "").strip()
                for name in (
                    "TOAPIS_KEY",
                    "TOAPIS_API_KEY",
                    "toapis_api_key",
                )
                if os.getenv(name, "").strip()
            ),
            None,
        )
        return cls(
            api_login=login,
            api_password=password,
            toapis_api_key=toapis_key,
            **overrides,
        )
