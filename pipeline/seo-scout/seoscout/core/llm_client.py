"""
LLM API Client — async batch generation with retry logic.

Shared by generate and translate stages. All config from Config class (.env).
"""

import asyncio
import aiohttp
import json
import time
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import Config


QUOTA_ERROR_MARKERS = (
    "insufficient_user_quota",
    "用户额度不足",
    "预扣费额度失败",
)


class LLMClient:
    """Async LLM API client with retry, stats, and batch support."""

    def __init__(self):
        self.api_keys = list(dict.fromkeys(Config.LLM_API_KEYS or [Config.LLM_API_KEY]))
        self.base_url = Config.LLM_API_BASE_URL.rstrip('/')
        self.api_url = f"{self.base_url}/chat/completions"
        self.model = Config.LLM_MODEL
        self.temperature = Config.LLM_TEMPERATURE
        self.max_tokens = Config.LLM_MAX_TOKENS
        self.frequency_penalty = Config.LLM_FREQUENCY_PENALTY
        self.presence_penalty = Config.LLM_PRESENCE_PENALTY
        self.timeout_seconds = Config.LLM_TIMEOUT
        self.retry_attempts = Config.LLM_RETRY_ATTEMPTS
        self.retry_delay = Config.LLM_RETRY_DELAY

        self._key_index = 0
        self._exhausted_keys: set[str] = set()
        self._permit_url = os.getenv("GAMEWIKI_PERMIT_URL", "").rstrip("/")
        self._permit_token = os.getenv("GAMEWIKI_PERMIT_TOKEN", "")

        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_tokens': 0,
            'start_time': None,
            'end_time': None,
        }

    # ── key rotation ────────────────────────────────────────────

    def _next_key(self) -> str:
        """轮询取下一个 key。并发请求各自推进游标，天然把任务打散到不同 key 上。"""
        for _ in range(len(self.api_keys)):
            key = self.api_keys[self._key_index % len(self.api_keys)]
            self._key_index += 1
            if key not in self._exhausted_keys:
                return key
        raise RuntimeError("All configured LLM API keys have insufficient quota")

    def _has_available_key(self) -> bool:
        return any(key not in self._exhausted_keys for key in self.api_keys)

    def _headers(self, api_key: str) -> Dict:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    @asynccontextmanager
    async def _shared_permit(self, session: aiohttp.ClientSession, api_key: str):
        if not self._permit_url:
            yield
            return
        slot = self.api_keys.index(api_key) + 1
        headers = {"Authorization": f"Bearer {self._permit_token}"}
        async with session.post(
            f"{self._permit_url}/acquire",
            json={"resources": ["llm", f"llm-key-{slot}"]},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=3600),
        ) as response:
            response.raise_for_status()
            lease = (await response.json())["lease"]
        try:
            yield
        finally:
            async with session.post(
                f"{self._permit_url}/release",
                json={"lease": lease},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()

    # ── single request ──────────────────────────────────────────

    async def generate_single(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
        meta: Dict = None,
        system: str = None,
        reasoning_effort: str = None,
        max_tokens: int = None,
        length_retry_instruction: str = None,
    ) -> Optional[str]:
        """Send a single prompt, return content string or None."""
        self.stats['total_requests'] += 1
        label = (meta or {}).get('keyword', 'unknown')

        active_prompt = prompt
        completion_limit = max_tokens or self.max_tokens

        attempt_limit = max(self.retry_attempts, len(self.api_keys))
        for attempt in range(attempt_limit):
            try:
                api_key = self._next_key()
            except RuntimeError as exc:
                print(f"  ❌ {label}: {exc}")
                self.stats['failed_requests'] += 1
                return None
            try:
                payload = {
                    "model": self.model,
                    "max_tokens": completion_limit,
                    "temperature": self.temperature,
                    "frequency_penalty": self.frequency_penalty,
                    "presence_penalty": self.presence_penalty,
                    "messages": [
                        {
                            "role": "system",
                            "content": system or "You are a professional SEO content writer.",
                        },
                        {"role": "user", "content": active_prompt},
                    ],
                    "stream": False,
                }
                effective_reasoning = (
                    Config.LLM_REASONING_EFFORT
                    if reasoning_effort is None
                    else reasoning_effort
                )
                if effective_reasoning:
                    payload["reasoning_effort"] = effective_reasoning

                async with self._shared_permit(session, api_key), session.post(
                    self.api_url,
                    json=payload,
                    headers=self._headers(api_key),
                    timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._save_debug(meta or {}, data, attempt=attempt + 1)
                        choice = data['choices'][0]
                        content = choice['message']['content']
                        finish_reason = choice.get('finish_reason')

                        if 'usage' in data:
                            self.stats['total_tokens'] += data['usage'].get('total_tokens', 0)

                        if not content or not content.strip():
                            print(f"  ⚠️  Empty response for {label} (attempt {attempt+1}/{attempt_limit})")
                            if attempt < attempt_limit - 1:
                                await asyncio.sleep(self.retry_delay * (attempt + 1))
                                continue
                            self.stats['failed_requests'] += 1
                            return None

                        if finish_reason and finish_reason != 'stop':
                            print(
                                f"  ⚠️  Incomplete response for {label}: "
                                f"finish_reason={finish_reason} "
                                f"(attempt {attempt+1}/{attempt_limit})"
                            )
                            if attempt < attempt_limit - 1:
                                if finish_reason == 'length':
                                    retry_instruction = length_retry_instruction or (
                                        "The previous response was truncated. Regenerate the complete "
                                        "answer from scratch, be substantially more concise, and avoid "
                                        "repetitive formatting or padded whitespace."
                                    )
                                    active_prompt = (
                                        prompt
                                        + "\n\n=== RETRY AFTER TRUNCATION ===\n"
                                        + retry_instruction.strip()
                                    )
                                    print(f"  ↪️  Retrying {label} with compact fallback instructions")
                                await asyncio.sleep(self.retry_delay * (attempt + 1))
                                continue
                            self.stats['failed_requests'] += 1
                            return None

                        self.stats['successful_requests'] += 1
                        return content

                    elif resp.status == 429:
                        wait = self.retry_delay * (attempt + 1) * 2
                        print(f"  ⚠️  Rate limited for {label}, waiting {wait}s...")
                        await asyncio.sleep(wait)
                        continue

                    else:
                        err = await resp.text()
                        if resp.status in {402, 403} and any(
                            marker in err for marker in QUOTA_ERROR_MARKERS
                        ):
                            self._exhausted_keys.add(api_key)
                            slot = self.api_keys.index(api_key) + 1
                            print(
                                f"  ❌ LLM key slot {slot} has insufficient quota "
                                f"for {label}; disabling it for this run"
                            )
                            if self._has_available_key() and attempt < attempt_limit - 1:
                                continue
                            self.stats['failed_requests'] += 1
                            return None
                        print(f"  ❌ API {resp.status} for {label}: {err[:300]}")
                        if attempt < attempt_limit - 1:
                            await asyncio.sleep(self.retry_delay * (attempt + 1))
                            continue
                        self.stats['failed_requests'] += 1
                        return None

            except asyncio.TimeoutError:
                print(f"  ⏱️  Timeout for {label} (attempt {attempt+1}/{attempt_limit})")
                if attempt < attempt_limit - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                self.stats['failed_requests'] += 1
                return None

            except Exception as e:
                print(f"  ❌ Exception for {label}: {e}")
                if attempt < attempt_limit - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                self.stats['failed_requests'] += 1
                return None

        self.stats['failed_requests'] += 1
        return None

    # ── batch ───────────────────────────────────────────────────

    async def generate_batch(
        self,
        prompts: List[Tuple[str, Dict]],
        batch_size: int = None,
        max_tokens: int = None,
        length_retry_instruction: str = None,
    ) -> List[Tuple[Dict, Optional[str]]]:
        """
        Batch-generate from list of (prompt, meta) tuples.
        Returns list of (meta, content_or_None) in same order.
        """
        if batch_size is None:
            batch_size = Config.GENERATE_BATCH_SIZE

        self.stats['start_time'] = time.time()
        results: List[Tuple[Dict, Optional[str]]] = [(meta, None) for _prompt, meta in prompts]

        async with aiohttp.ClientSession() as session:
            concurrency = max(1, min(batch_size, Config.GENERATE_CONCURRENT_LIMIT))
            semaphore = asyncio.Semaphore(concurrency)
            completed = 0
            completed_lock = asyncio.Lock()
            print(f"\n  🚦 Worker queue: {len(prompts)} items, concurrency={concurrency}")

            async def worker(index: int, prompt: str, meta: Dict):
                nonlocal completed
                async with semaphore:
                    if not self._has_available_key():
                        content = None
                    else:
                        content = await self.generate_single(
                            session,
                            prompt,
                            meta,
                            max_tokens=max_tokens,
                            length_retry_instruction=length_retry_instruction,
                        )
                    results[index] = (meta, content)
                async with completed_lock:
                    completed += 1
                    print(f"  ✅ {completed}/{len(prompts)} done")

            await asyncio.gather(*(worker(index, prompt, meta) for index, (prompt, meta) in enumerate(prompts)))

        self.stats['end_time'] = time.time()
        return results

    # ── debug ───────────────────────────────────────────────────

    def _save_debug(self, meta: Dict, data: Dict, attempt: int = None):
        try:
            debug_dir = Path(Config.LOG_DIR) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            keyword = meta.get('keyword', 'unknown')
            lang = meta.get('language', 'en')
            stem = f"{lang}_{keyword.replace(' ', '_')}"
            serialized = json.dumps(data, indent=2, ensure_ascii=False)
            latest = debug_dir / f"{stem}_response.json"
            latest.write_text(serialized, encoding='utf-8')
            if attempt is not None:
                attempt_file = debug_dir / f"{stem}_attempt_{attempt}_response.json"
                attempt_file.write_text(serialized, encoding='utf-8')
        except Exception:
            pass

    # ── stats ───────────────────────────────────────────────────

    def print_stats(self):
        s = self.stats
        duration = (s['end_time'] or time.time()) - (s['start_time'] or time.time())
        rate = s['total_requests'] / duration if duration > 0 else 0
        success_rate = (
            s['successful_requests'] / s['total_requests'] * 100
            if s['total_requests'] > 0 else 0
        )
        print(f"\n  📊 LLM API: {s['successful_requests']}/{s['total_requests']} ok "
              f"({success_rate:.0f}%) | {s['total_tokens']} tokens | {duration:.1f}s")
