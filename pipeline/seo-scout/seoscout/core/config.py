"""
Unified configuration management.

Two sources, deliberately kept separate:
  - .env          — secrets only (API keys/credentials). Gitignored, each
                     user/deployment fills in their own, never committed.
  - config.json    — everything else (tunable knobs: batch sizes, workers,
                     timeouts, model name, blocked domains, ...). Has no
                     secrets in it, so it's tracked in git and can be
                     committed/pushed/shared like any other source file —
                     no more copy-and-fill-in-forty-values step for a
                     teammate who just wants the same tuning you already
                     settled on.

Data is stored under OUTPUT_DIR/<project_name>/ for isolation. Each
project's keywords.json input is expected to live alongside it, e.g.
projects/<project_name>/keywords.json.
"""

import json
import os
import re
import sys
from dotenv import load_dotenv


def _load_config_file(path: str = "config.json") -> dict:
    """Read config.json from the current working directory. Missing file or
    invalid JSON both fall back to {} (every lookup below already has a
    hardcoded default) rather than crashing — config.json is optional."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️  Could not read {path} ({e}) — using built-in defaults")
        return {}


class _Tee:
    """Duplicates writes to multiple streams (e.g. console + log file)."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)

    def flush(self):
        for s in self.streams:
            s.flush()

    def isatty(self):
        return False


class Config:
    """Unified configuration management"""

    # Paths — set by init()
    DATA_DIR = None
    OUT_DIR = None
    BASE_DIR = None
    CACHE_DIR = None
    LOG_DIR = None

    # Set to True once console output has been mirrored to a log file
    # for this process (only done once per run, even across multiple
    # Config.init() calls within `seoscout run`).
    _logging_initialized = False

    # ============================================================
    # API Keys (loaded from .env in init())
    # ============================================================
    SERPER_API_KEY = ""
    JINA_API_KEY = ""

    # ============================================================
    # Output
    # ============================================================
    OUTPUT_DIR = "./projects"

    # ============================================================
    # YouTube configuration
    # ============================================================
    YOUTUBE_INITIAL_RESULTS = 2
    YOUTUBE_MAX_RESULTS = 1
    YOUTUBE_MAX_DURATION = 3600
    YOUTUBE_EXTRACT_TOP_K = 1

    YOUTUBE_SEARCH_WORKERS = 3
    YOUTUBE_EXTRACT_WORKERS = 5
    YOUTUBE_RETRIES = 3
    YOUTUBE_TIMEOUT = 180

    # DataForSEO (replaces yt-dlp + youtube_transcript_api)
    DATAFORSEO_LOGIN = ""
    DATAFORSEO_PASSWORD = ""
    DATAFORSEO_BASE_URL = "https://api.dataforseo.com"
    YOUTUBE_LOCATION_CODE = 2840
    YOUTUBE_LANGUAGE_CODE = "en"
    YOUTUBE_DEVICE = "desktop"
    YOUTUBE_OS = "windows"
    YOUTUBE_BLOCK_DEPTH = 10

    # ============================================================
    # Web configuration
    # ============================================================
    WEB_SEARCH_TOP_N = 10
    WEB_EXTRACT_TOP_K = 1
    WEB_EXTRACT_WORKERS = 20
    WEB_EXTRACT_RETRIES = 3
    WEB_SEARCH_CONCURRENCY = 5
    JINA_RPM = 200
    JINA_CONCURRENCY = 20

    # ============================================================
    # LLM API (generate + translate)
    # ============================================================
    LLM_API_KEY = ""
    LLM_API_KEYS = []
    LLM_API_BASE_URL = "https://api.apifast.tech/v1"
    LLM_MODEL = "gemini-2.5-flash"
    LLM_TEMPERATURE = 0.7
    LLM_MAX_TOKENS = 10000
    LLM_REASONING_EFFORT = "low"
    LLM_FREQUENCY_PENALTY = 0.3
    LLM_PRESENCE_PENALTY = 0.3
    LLM_TIMEOUT = 300
    LLM_RETRY_ATTEMPTS = 2
    LLM_RETRY_DELAY = 5

    # ============================================================
    # Generate concurrency
    # ============================================================
    GENERATE_MAX_TOKENS = 10000
    GENERATE_BATCH_SIZE = 100
    GENERATE_CONCURRENT_LIMIT = 10

    # ============================================================
    # Translate concurrency
    # ============================================================
    TRANSLATE_BATCH_SIZE = 10
    TRANSLATE_BATCH_DELAY = 1
    TRANSLATE_REASONING_EFFORT = "none"

    # ============================================================
    # General
    # ============================================================
    SEARCH_MAX_RETRIES = 3
    SEARCH_RETRY_DELAY = 2

    BLOCKED_DOMAINS = {"youtube.com", "youtu.be", "reddit.com", "discord.com"}

    _initialized = False

    @classmethod
    def init(cls, project: str):
        """
        Initialize config for a project.

        Args:
            project: Project name (e.g. "my-site"). Data will be stored
                     under OUTPUT_DIR/<project>/.
        """
        # .env → secrets only. config.json → everything else (tunables).
        load_dotenv()
        cfg = _load_config_file()
        yt_cfg = cfg.get("youtube", {})
        web_cfg = cfg.get("web", {})
        llm_cfg = cfg.get("llm", {})
        gen_cfg = cfg.get("generate", {})
        xlate_cfg = cfg.get("translate", {})
        search_cfg = cfg.get("search", {})

        # Sanitize project name
        project_dir = project.replace('.', '_').replace('/', '_')

        # Read output root.  The orchestrator can bind SEO Scout to an exact
        # per-game directory; this avoids leaking generated content back into
        # the clean source repository.
        cls.OUTPUT_DIR = cfg.get("output_dir", "./projects")

        # Set up project paths
        exact_project_dir = os.getenv("SEOSCOUT_PROJECT_DIR", "").strip()
        cls.DATA_DIR = (
            os.path.abspath(os.path.expanduser(exact_project_dir))
            if exact_project_dir
            else os.path.join(cls.OUTPUT_DIR, project_dir)
        )
        cls.OUT_DIR = os.path.join(cls.DATA_DIR, "out")
        cls.BASE_DIR = cls.OUT_DIR
        cls.CACHE_DIR = os.path.join(cls.OUT_DIR, "cache")
        cls.LOG_DIR = os.path.join(cls.DATA_DIR, "logs")

        os.makedirs(cls.OUT_DIR, exist_ok=True)
        os.makedirs(cls.CACHE_DIR, exist_ok=True)
        os.makedirs(cls.LOG_DIR, exist_ok=True)

        # API Keys (secrets — .env only)
        cls.SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
        cls.JINA_API_KEY = os.getenv("JINA_API_KEY", "")

        # YouTube
        cls.YOUTUBE_INITIAL_RESULTS = int(yt_cfg.get("initial_search_results", 2))
        cls.YOUTUBE_MAX_RESULTS = int(yt_cfg.get("max_results_after_filter", 1))
        cls.YOUTUBE_MAX_DURATION = int(yt_cfg.get("max_duration", 3600))
        cls.YOUTUBE_EXTRACT_TOP_K = int(yt_cfg.get("extract_top_k", 1))

        cls.YOUTUBE_SEARCH_WORKERS = int(yt_cfg.get("search_workers", 3))
        cls.YOUTUBE_EXTRACT_WORKERS = int(yt_cfg.get("transcript_workers", 5))
        cls.YOUTUBE_RETRIES = int(yt_cfg.get("transcript_retries", 3))
        cls.YOUTUBE_TIMEOUT = int(yt_cfg.get("search_timeout", 180))

        # DataForSEO — credentials are secrets (.env), everything else is config.json
        cls.DATAFORSEO_LOGIN = os.getenv("DATAFORSEO_LOGIN", "")
        cls.DATAFORSEO_PASSWORD = os.getenv("DATAFORSEO_PASSWORD", "")
        cls.DATAFORSEO_BASE_URL = yt_cfg.get("base_url", "https://api.dataforseo.com")
        cls.YOUTUBE_LOCATION_CODE = int(yt_cfg.get("location_code", 2840))
        cls.YOUTUBE_LANGUAGE_CODE = yt_cfg.get("language_code", "en")
        cls.YOUTUBE_DEVICE = yt_cfg.get("device", "desktop")
        cls.YOUTUBE_OS = yt_cfg.get("os", "windows")
        cls.YOUTUBE_BLOCK_DEPTH = int(yt_cfg.get("block_depth", 10))

        # Web
        cls.WEB_SEARCH_TOP_N = int(web_cfg.get("search_top_n", 10))
        cls.WEB_EXTRACT_TOP_K = int(web_cfg.get("extract_top_k", 1))
        cls.WEB_EXTRACT_WORKERS = int(web_cfg.get("jina_concurrency", 20))
        cls.WEB_EXTRACT_RETRIES = int(web_cfg.get("extract_retries", 3))
        cls.WEB_SEARCH_CONCURRENCY = int(web_cfg.get("search_concurrency", 5))
        cls.JINA_RPM = int(web_cfg.get("jina_rpm", 200))
        cls.JINA_CONCURRENCY = int(web_cfg.get("jina_concurrency", 20))

        # General
        cls.SEARCH_MAX_RETRIES = int(search_cfg.get("max_retries", 3))
        cls.SEARCH_RETRY_DELAY = int(search_cfg.get("retry_delay", 2))

        # LLM API (generate + translate) — keys are secrets (.env), rest is config.json
        cls.LLM_API_KEY = os.getenv("LLM_API_KEY", "")
        # 支持多个 key 轮询（LLM_API_KEY_1, LLM_API_KEY_2, ...），
        # 用于分摊限速/瞬时错误。没配置多 key 时退回单一 LLM_API_KEY。
        numbered = []
        for name, value in os.environ.items():
            match = re.fullmatch(r"LLM_API_KEY_(\d+)", name)
            if match and value.strip():
                numbered.append((int(match.group(1)), value.strip()))
        keys = [value for _slot, value in sorted(numbered)]
        cls.LLM_API_KEYS = keys or ([cls.LLM_API_KEY] if cls.LLM_API_KEY else [])
        cls.LLM_API_BASE_URL = llm_cfg.get("base_url", "https://api.apifast.tech/v1")
        cls.LLM_MODEL = llm_cfg.get("model", "gemini-2.5-flash")
        cls.LLM_TEMPERATURE = float(llm_cfg.get("temperature", 0.7))
        cls.LLM_MAX_TOKENS = int(llm_cfg.get("max_tokens", 10000))
        cls.LLM_REASONING_EFFORT = str(llm_cfg.get("reasoning_effort", "low")).strip()
        cls.LLM_FREQUENCY_PENALTY = float(llm_cfg.get("frequency_penalty", 0.3))
        cls.LLM_PRESENCE_PENALTY = float(llm_cfg.get("presence_penalty", 0.3))
        cls.LLM_TIMEOUT = int(llm_cfg.get("timeout", 300))
        cls.LLM_RETRY_ATTEMPTS = int(llm_cfg.get("retry_attempts", 2))
        cls.LLM_RETRY_DELAY = int(llm_cfg.get("retry_delay", 5))

        # Generate concurrency
        cls.GENERATE_MAX_TOKENS = int(
            gen_cfg.get("max_tokens", min(10000, cls.LLM_MAX_TOKENS))
        )
        cls.GENERATE_BATCH_SIZE = int(gen_cfg.get("batch_size", 100))
        cls.GENERATE_CONCURRENT_LIMIT = int(gen_cfg.get("concurrent_limit", 10))

        # Translate concurrency
        cls.TRANSLATE_BATCH_SIZE = int(xlate_cfg.get("batch_size", 10))
        cls.TRANSLATE_BATCH_DELAY = int(xlate_cfg.get("batch_delay", 1))
        cls.TRANSLATE_REASONING_EFFORT = str(
            xlate_cfg.get("reasoning_effort", "none")
        ).strip()

        cls.BLOCKED_DOMAINS = set(
            d.strip()
            for d in cfg.get("blocked_domains", ["youtube.com", "youtu.be", "reddit.com", "discord.com"])
            if d.strip()
        )

        cls._initialized = True

        # Mirror all console output to a log file for this run. Only done
        # once per process — `seoscout run` calls Config.init() again for
        # each step (classify/search/collect/...), and we want one fresh
        # log file per invocation, not one per step.
        if not cls._logging_initialized:
            log_path = os.path.join(cls.LOG_DIR, "seoscout.log")
            log_file = open(log_path, "w", encoding="utf-8")
            sys.stdout = _Tee(sys.stdout, log_file)
            sys.stderr = _Tee(sys.stderr, log_file)
            cls._logging_initialized = True

    @classmethod
    def validate(cls) -> bool:
        errors = []

        if not cls.SERPER_API_KEY:
            errors.append("SERPER_API_KEY not set")

        if not cls.JINA_API_KEY:
            errors.append("JINA_API_KEY not set (optional, but recommended for higher rate limits)")

        if not cls.DATAFORSEO_LOGIN or not cls.DATAFORSEO_PASSWORD:
            errors.append("DATAFORSEO_LOGIN/DATAFORSEO_PASSWORD not set (required for YouTube search/collect)")

        if errors:
            print("⚠️  Config warnings:")
            for error in errors:
                print(f"  - {error}")
            return False

        return True

    @classmethod
    def print_summary(cls):
        print("\n" + "=" * 70)
        print("  Configuration")
        print("=" * 70)
        print(f"Data dir:    {cls.DATA_DIR}")
        print(f"Output dir:  {cls.OUT_DIR}")
        print(f"\nYouTube:")
        print(f"  - Initial results: {cls.YOUTUBE_INITIAL_RESULTS}")
        print(f"  - Max results:     {cls.YOUTUBE_MAX_RESULTS}")
        print(f"  - Max duration:    {cls.YOUTUBE_MAX_DURATION}s")
        print(f"  - Extract top-k:   {cls.YOUTUBE_EXTRACT_TOP_K}")
        print(f"  - Search workers:  {cls.YOUTUBE_SEARCH_WORKERS}")
        print(f"  - Extract workers: {cls.YOUTUBE_EXTRACT_WORKERS}")
        print(f"\nWeb:")
        print(f"  - Search results:  {cls.WEB_SEARCH_TOP_N}")
        print(f"  - Search workers:  {cls.WEB_SEARCH_CONCURRENCY}")
        print(f"  - Extract top-k:   {cls.WEB_EXTRACT_TOP_K}")
        print(f"  - Jina RPM:        {cls.JINA_RPM}")
        print(f"  - Jina concurrency:{cls.JINA_CONCURRENCY}")
        print(f"\nGeneral:")
        print(f"  - Blocked domains: {len(cls.BLOCKED_DOMAINS)}")
        print(f"  - Search retries:  {cls.SEARCH_MAX_RETRIES}")
        print(f"\nLLM:")
        print(f"  - Model:           {cls.LLM_MODEL}")
        print(f"  - API keys:        {len(cls.LLM_API_KEYS)}")
        print(f"  - API base:        {cls.LLM_API_BASE_URL}")
        print(f"  - Max tokens:      {cls.LLM_MAX_TOKENS}")
        print(f"  - Reasoning effort:{cls.LLM_REASONING_EFFORT or 'provider default'}")
        print(f"  - Gen max tokens:  {cls.GENERATE_MAX_TOKENS}")
        print(f"  - Gen batch size:  {cls.GENERATE_BATCH_SIZE}")
        print(f"  - Xlate batch:     {cls.TRANSLATE_BATCH_SIZE}")
        print(f"  - Xlate reasoning: {cls.TRANSLATE_REASONING_EFFORT or 'provider default'}")
        print("=" * 70 + "\n")
