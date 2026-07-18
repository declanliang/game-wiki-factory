"""
Unified configuration management.

Loads all config from a .env file in the current working directory.
Data is stored under OUTPUT_DIR/<project_name>/ for isolation. Each
project's keywords.json input is expected to live alongside it, e.g.
projects/<project_name>/keywords.json.
"""

import os
import sys
from dotenv import load_dotenv


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
    LLM_FREQUENCY_PENALTY = 0.3
    LLM_PRESENCE_PENALTY = 0.3
    LLM_TIMEOUT = 300
    LLM_RETRY_ATTEMPTS = 2
    LLM_RETRY_DELAY = 5

    # ============================================================
    # Generate concurrency
    # ============================================================
    GENERATE_BATCH_SIZE = 100
    GENERATE_CONCURRENT_LIMIT = 10

    # ============================================================
    # Translate concurrency
    # ============================================================
    TRANSLATE_BATCH_SIZE = 10
    TRANSLATE_BATCH_DELAY = 1

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
        # Load .env from current working directory
        load_dotenv()

        # Sanitize project name
        project_dir = project.replace('.', '_').replace('/', '_')

        # Read output root
        cls.OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./projects")

        # Set up project paths
        cls.DATA_DIR = os.path.join(cls.OUTPUT_DIR, project_dir)
        cls.OUT_DIR = os.path.join(cls.DATA_DIR, "out")
        cls.BASE_DIR = cls.OUT_DIR
        cls.CACHE_DIR = os.path.join(cls.OUT_DIR, "cache")
        cls.LOG_DIR = os.path.join(cls.DATA_DIR, "logs")

        os.makedirs(cls.OUT_DIR, exist_ok=True)
        os.makedirs(cls.CACHE_DIR, exist_ok=True)
        os.makedirs(cls.LOG_DIR, exist_ok=True)

        # API Keys
        cls.SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
        cls.JINA_API_KEY = os.getenv("JINA_API_KEY", "")

        # YouTube
        cls.YOUTUBE_INITIAL_RESULTS = int(os.getenv("YOUTUBE_INITIAL_SEARCH_RESULTS", "2"))
        cls.YOUTUBE_MAX_RESULTS = int(os.getenv("YOUTUBE_MAX_RESULTS_AFTER_FILTER", "1"))
        cls.YOUTUBE_MAX_DURATION = int(os.getenv("YOUTUBE_MAX_DURATION", "3600"))
        cls.YOUTUBE_EXTRACT_TOP_K = int(os.getenv("YOUTUBE_EXTRACT_TOP_K", "1"))

        cls.YOUTUBE_SEARCH_WORKERS = int(os.getenv("YOUTUBE_SEARCH_WORKERS", "3"))
        cls.YOUTUBE_EXTRACT_WORKERS = int(os.getenv("YOUTUBE_TRANSCRIPT_WORKERS", "5"))
        cls.YOUTUBE_RETRIES = int(os.getenv("YOUTUBE_TRANSCRIPT_RETRIES", "3"))
        cls.YOUTUBE_TIMEOUT = int(os.getenv("YOUTUBE_SEARCH_TIMEOUT", "180"))

        # DataForSEO
        cls.DATAFORSEO_LOGIN = os.getenv("DATAFORSEO_LOGIN", "")
        cls.DATAFORSEO_PASSWORD = os.getenv("DATAFORSEO_PASSWORD", "")
        cls.DATAFORSEO_BASE_URL = os.getenv("DATAFORSEO_BASE_URL", "https://api.dataforseo.com")
        cls.YOUTUBE_LOCATION_CODE = int(os.getenv("YOUTUBE_LOCATION_CODE", "2840"))
        cls.YOUTUBE_LANGUAGE_CODE = os.getenv("YOUTUBE_LANGUAGE_CODE", "en")
        cls.YOUTUBE_DEVICE = os.getenv("YOUTUBE_DEVICE", "desktop")
        cls.YOUTUBE_OS = os.getenv("YOUTUBE_OS", "windows")
        cls.YOUTUBE_BLOCK_DEPTH = int(os.getenv("YOUTUBE_BLOCK_DEPTH", "10"))

        # Web
        cls.WEB_SEARCH_TOP_N = int(os.getenv("WEB_SEARCH_TOP_N", "10"))
        cls.WEB_EXTRACT_TOP_K = int(os.getenv("WEB_EXTRACT_TOP_K", "1"))
        cls.WEB_EXTRACT_WORKERS = int(os.getenv("JINA_CONCURRENCY", "20"))
        cls.WEB_EXTRACT_RETRIES = int(os.getenv("WEB_EXTRACT_RETRIES", "3"))
        cls.WEB_SEARCH_CONCURRENCY = int(os.getenv("WEB_SEARCH_CONCURRENCY", "5"))
        cls.JINA_RPM = int(os.getenv("JINA_RPM", "200"))
        cls.JINA_CONCURRENCY = int(os.getenv("JINA_CONCURRENCY", "20"))

        # General
        cls.SEARCH_MAX_RETRIES = int(os.getenv("SEARCH_MAX_RETRIES", "3"))
        cls.SEARCH_RETRY_DELAY = int(os.getenv("SEARCH_RETRY_DELAY", "2"))

        # LLM API (generate + translate)
        cls.LLM_API_KEY = os.getenv("LLM_API_KEY", "")
        # 支持多个 key 轮询（LLM_API_KEY_1, LLM_API_KEY_2, ...），
        # 用于分摊限速/瞬时错误。没配置多 key 时退回单一 LLM_API_KEY。
        keys = []
        i = 1
        while True:
            k = os.getenv(f"LLM_API_KEY_{i}", "").strip()
            if not k:
                break
            keys.append(k)
            i += 1
        cls.LLM_API_KEYS = keys or ([cls.LLM_API_KEY] if cls.LLM_API_KEY else [])
        cls.LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL", "https://api.apifast.tech/v1")
        cls.LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
        cls.LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
        cls.LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "10000"))
        cls.LLM_FREQUENCY_PENALTY = float(os.getenv("LLM_FREQUENCY_PENALTY", "0.3"))
        cls.LLM_PRESENCE_PENALTY = float(os.getenv("LLM_PRESENCE_PENALTY", "0.3"))
        cls.LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "300"))
        cls.LLM_RETRY_ATTEMPTS = int(os.getenv("LLM_RETRY_ATTEMPTS", "2"))
        cls.LLM_RETRY_DELAY = int(os.getenv("LLM_RETRY_DELAY", "5"))

        # Generate concurrency
        cls.GENERATE_BATCH_SIZE = int(os.getenv("GENERATE_BATCH_SIZE", "100"))
        cls.GENERATE_CONCURRENT_LIMIT = int(os.getenv("GENERATE_CONCURRENT_LIMIT", "10"))

        # Translate concurrency
        cls.TRANSLATE_BATCH_SIZE = int(os.getenv("TRANSLATE_BATCH_SIZE", "10"))
        cls.TRANSLATE_BATCH_DELAY = int(os.getenv("TRANSLATE_BATCH_DELAY", "1"))

        cls.BLOCKED_DOMAINS = set(
            d.strip()
            for d in os.getenv("BLOCKED_DOMAINS",
                "youtube.com,youtu.be,reddit.com,discord.com").split(",")
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
        print(f"  - Gen batch size:  {cls.GENERATE_BATCH_SIZE}")
        print(f"  - Xlate batch:     {cls.TRANSLATE_BATCH_SIZE}")
        print("=" * 70 + "\n")
