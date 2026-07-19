"""
DataForSEO YouTube SERP API 客户端

只封装本项目需要的两个接口：YouTube 搜索、YouTube 字幕。
不做数据库持久化、不做任务队列——由调用方（youtube.py）负责缓存和重试编排。
"""

import asyncio
import base64
from typing import Optional

import aiohttp

from .config import Config


class DataForSEOError(Exception):
    """不可重试的 DataForSEO 错误（如认证失败）"""
    pass


class DataForSEOClient:
    """DataForSEO SERP API 的轻量异步客户端"""

    def __init__(self):
        self.base_url = Config.DATAFORSEO_BASE_URL.rstrip("/")
        auth = f"{Config.DATAFORSEO_LOGIN}:{Config.DATAFORSEO_PASSWORD}"
        self._auth_header = "Basic " + base64.b64encode(auth.encode()).decode()
        self.total_cost = 0.0
        self.total_requests = 0

    def _headers(self) -> dict:
        return {
            "Authorization": self._auth_header,
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, payload: list) -> dict:
        """
        POST 请求 + 双层 status_code 容错解析。

        401/403 视为凭证/权限错误，不重试，直接抛出。
        429/5xx/超时由调用方按 Config.YOUTUBE_RETRIES 重试。
        """
        url = f"{self.base_url}{path}"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=Config.YOUTUBE_TIMEOUT),
            ) as response:
                if response.status in (401, 403):
                    raise DataForSEOError(f"DataForSEO 认证失败: HTTP {response.status}")

                if response.status == 429:
                    retry_after = response.headers.get("Retry-After")
                    raise Exception(f"HTTP 429 Rate limited (Retry-After={retry_after})")

                if response.status >= 500:
                    raise Exception(f"DataForSEO 服务端错误: HTTP {response.status}")

                if response.status != 200:
                    text = await response.text()
                    raise Exception(f"DataForSEO 返回 HTTP {response.status}: {text[:300]}")

                data = await response.json()

        self.total_requests += 1
        for task in (data.get("tasks") or []):
            cost = task.get("cost")
            if isinstance(cost, (int, float)):
                self.total_cost += cost

        if data.get("status_code") != 20000:
            raise Exception(
                f"DataForSEO API 错误 {data.get('status_code')}: {data.get('status_message')}"
            )

        return data

    async def search_youtube(
        self,
        keyword: str,
        *,
        location_code: Optional[int] = None,
        language_code: Optional[str] = None,
        device: Optional[str] = None,
        os_name: Optional[str] = None,
        block_depth: Optional[int] = None,
    ) -> dict:
        payload = [{
            "keyword": keyword,
            "location_code": location_code or Config.YOUTUBE_LOCATION_CODE,
            "language_code": language_code or Config.YOUTUBE_LANGUAGE_CODE,
            "device": device or Config.YOUTUBE_DEVICE,
            "os": os_name or Config.YOUTUBE_OS,
            "block_depth": block_depth or Config.YOUTUBE_BLOCK_DEPTH,
        }]
        return await self._post("/v3/serp/youtube/organic/live/advanced", payload)

    async def get_subtitles(
        self,
        video_id: str,
        *,
        location_code: Optional[int] = None,
        language_code: Optional[str] = None,
        subtitles_language: Optional[str] = None,
    ) -> dict:
        item = {
            "video_id": video_id,
            "location_code": location_code or Config.YOUTUBE_LOCATION_CODE,
            "language_code": language_code or Config.YOUTUBE_LANGUAGE_CODE,
            "device": Config.YOUTUBE_DEVICE,
            "os": Config.YOUTUBE_OS,
        }
        if subtitles_language:
            item["subtitles_language"] = subtitles_language

        return await self._post("/v3/serp/youtube/video_subtitles/live/advanced", [item])


def extract_youtube_videos(response: dict) -> list:
    """从搜索响应中提取 youtube_video 类型的条目，容错解析"""
    videos = []

    for task in (response.get("tasks") or []):
        if task.get("status_code") != 20000:
            continue

        for result in (task.get("result") or []):
            for item in (result.get("items") or []):
                if item.get("type") != "youtube_video":
                    continue

                video_id = item.get("video_id")
                title = item.get("title")
                url = item.get("url")
                if not video_id or not title or not url:
                    continue

                videos.append({
                    "video_id": video_id,
                    "title": title,
                    "url": url,
                    "channel": item.get("channel_name", ""),
                    "view_count": item.get("views_count") or 0,
                    "duration_seconds": (
                        item.get("duration_time_seconds")
                        or item.get("duration_time_second")
                        or 0
                    ),
                })

    return videos


def extract_transcript(response: dict) -> dict:
    """从字幕响应中提取并规范化文本，容错解析"""
    tasks = response.get("tasks") or []
    if not tasks:
        return {"status": "api_error", "text": ""}

    task = tasks[0]
    if task.get("status_code") != 20000:
        return {"status": "api_error", "text": ""}

    results = task.get("result") or []
    if not results:
        return {"status": "unavailable", "text": ""}

    result = results[0]
    if result.get("unsupported_language"):
        return {"status": "unsupported_language", "text": ""}

    segments = sorted(
        result.get("items") or [],
        key=lambda x: x.get("rank_absolute") or 0,
    )

    texts = []
    previous = None
    for segment in segments:
        text = " ".join((segment.get("text") or "").split())
        if not text or text == previous:
            continue
        texts.append(text)
        previous = text

    status = "available" if texts else "unavailable"
    return {"status": status, "text": " ".join(texts)}
