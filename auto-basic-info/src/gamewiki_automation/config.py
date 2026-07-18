from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    toapis_api_key: str | None
    perplexity_api_key: str | None
    toapis_model: str
    toapis_web_model: str
    toapis_reasoning_effort: str
    perplexity_model: str
    output_dir: Path
    cache_dir: Path
    request_timeout: int
    refresh: bool = False

    @classmethod
    def load(cls, root: Path | None = None, refresh: bool = False) -> "Settings":
        root = (root or Path.cwd()).resolve()
        load_dotenv(root / ".env", override=False)
        return cls(
            toapis_api_key=(
                os.getenv("TOAPIS_API_KEY")
                or os.getenv("toapis_API_KEY")
                or os.getenv("toapis_api_key")
                or None
            ),
            perplexity_api_key=(
                os.getenv("PERPLEXITY_API_KEY")
                or os.getenv("perplexity_api_key")
                or None
            ),
            toapis_model=os.getenv("TOAPIS_MODEL", "gpt-5.3-codex-official"),
            toapis_web_model=os.getenv("TOAPIS_WEB_MODEL", "gpt-5.3-codex-official"),
            toapis_reasoning_effort=os.getenv("TOAPIS_REASONING_EFFORT", "low"),
            perplexity_model=os.getenv("PERPLEXITY_MODEL", "sonar-pro"),
            output_dir=root / os.getenv("GAMEWIKI_OUTPUT_DIR", "output"),
            cache_dir=root / os.getenv("GAMEWIKI_CACHE_DIR", ".cache"),
            request_timeout=int(os.getenv("GAMEWIKI_REQUEST_TIMEOUT", "300")),
            refresh=refresh,
        )
