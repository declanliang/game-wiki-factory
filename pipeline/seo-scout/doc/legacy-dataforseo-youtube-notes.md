# DataForSEO YouTube 视频搜索与字幕采集系统

## 技术设计与 AI 开发规格说明书

*版本：1.0  
日期：2026-07-15  
目标读者：开发 AI、后端工程师、测试工程师*

# 1. 项目概述

本系统接收一个或多个关键词，通过 DataForSEO SERP API 搜索对应的 YouTube 视频，保存视频标题、URL、video_id、排名及可用元数据，然后针对每个视频调用 YouTube Video Subtitles API，提取现有字幕并合并为可分析的完整文本。系统不使用 yt-dlp，不直接访问或抓取 YouTube，因此无需自行维护代理、Cookie、IP 池和反爬逻辑。

## 1.1 核心目标
- 输入关键词，按指定国家、语言和设备查询 YouTube 搜索结果。
- 提取并持久化视频标题、URL、video_id、频道、排名、播放量、发布时间、时长等可用字段。
- 对去重后的视频逐个请求字幕，并保存原始分段字幕、完整字幕文本和字幕状态。
- 支持批量关键词、并发控制、失败重试、断点续跑、成本统计和结构化导出。
- 输出适合后续关键词提取、内容分析、向量化或大模型处理的数据。

## 1.2 非目标
- 不下载视频或音频文件。
- 不对无字幕视频执行语音识别；DataForSEO 未返回字幕时，仅记录无字幕状态。
- 不绕过地区限制、登录限制、私密视频或平台访问控制。
- 第一版不实现前端管理界面，优先提供 CLI 或 HTTP API。

# 2. 官方接口与关键事实

| 用途 | HTTP 方法与路径 | 关键输入 | 关键输出 |
| --- | --- | --- | --- |
| 关键词搜索视频 | POST /v3/serp/youtube/organic/live/advanced | keyword, location_code, language_code, block_depth | youtube_video items，包括 title、url、video_id 等 |
| 获取视频字幕 | POST /v3/serp/youtube/video_subtitles/live/advanced | video_id, location_code, language_code，可选字幕语言参数 | title、origin_language、subtitles_count、items 分段字幕 |
| 可选：视频详情 | POST /v3/serp/youtube/video_info/live/advanced | video_id, location_code, language_code | 视频详情及可用字幕语言信息 |

官方文档说明：YouTube Organic Live Advanced 返回指定位置和语言下的实时 YouTube 搜索结果；默认 block_depth 为 20，最大为 200，超过 20 可能产生额外计费。Video Subtitles Live Advanced 根据 video_id 返回观看页中的字幕文本、语言和时间信息。每次 Live 请求均单独计费。

# 3. 推荐系统架构

```text
Client / CLI
    |
    v
Job Service
    |-- Input validation
    |-- Job state management
    |-- Cost and quota guard
    |
    +--> DataForSEO Search Client
    |       POST /youtube/organic/live/advanced
    |
    +--> Result Normalizer and Video Deduplicator
    |
    +--> Subtitle Worker Pool
    |       POST /youtube/video_subtitles/live/advanced
    |
    +--> Storage
            jobs
            keyword_searches
            videos
            keyword_videos
            subtitle_tracks
            subtitle_segments
```

## 3.1 推荐技术栈

| 组件 | 建议 |
| --- | --- |
| 语言 | Python 3.12+ |
| HTTP 客户端 | httpx，支持超时、连接池和异步并发 |
| 数据校验 | Pydantic 2 |
| 数据库 | PostgreSQL；本地原型可使用 SQLite |
| ORM | SQLAlchemy 2 或直接使用 PostgreSQL 驱动 |
| 任务队列 | 小规模可用 asyncio；生产批量任务可用 Celery、RQ 或 Dramatiq |
| 日志 | 结构化 JSON 日志，严禁输出 API password |
| 测试 | pytest、respx 或 pytest-httpx |

# 4. 配置设计

```dotenv
DATAFORSEO_LOGIN=your_api_login
DATAFORSEO_PASSWORD=your_api_password
DATAFORSEO_BASE_URL=https://api.dataforseo.com
YOUTUBE_LOCATION_CODE=2840
YOUTUBE_LANGUAGE_CODE=en
YOUTUBE_DEVICE=desktop
YOUTUBE_OS=windows
YOUTUBE_BLOCK_DEPTH=20
SEARCH_CONCURRENCY=3
SUBTITLE_CONCURRENCY=5
HTTP_CONNECT_TIMEOUT_SECONDS=10
HTTP_READ_TIMEOUT_SECONDS=60
MAX_RETRIES=4
RETRY_BASE_DELAY_SECONDS=1
MAX_VIDEOS_PER_KEYWORD=20
MAX_TOTAL_VIDEOS_PER_JOB=500
```

凭证必须从环境变量或密钥管理服务读取，不得写入代码、配置仓库、日志、异常消息或 API 响应。

# 5. 输入与输出契约

## 5.1 作业输入

```json
{
  "keywords": [
    "animal hospital guide",
    "animal hospital classes"
  ],
  "location_code": 2840,
  "language_code": "en",
  "device": "desktop",
  "os": "windows",
  "block_depth": 20,
  "max_videos_per_keyword": 10,
  "fetch_subtitles": true,
  "subtitles_language": "en",
  "subtitles_translate_language": null
}
```

## 5.2 参数规则

| 字段 | 规则 |
| --- | --- |
| keywords | 必填；去除首尾空格和空值；保留原始顺序；建议每个作业不超过 100 个 |
| location_code | 默认 2840（United States）；必须可配置 |
| language_code | 默认 en；必须可配置 |
| block_depth | 默认 20；范围 1-200；第一版建议限制到 20 以控制成本 |
| max_videos_per_keyword | 不得大于 block_depth；默认 10 |
| subtitles_language | 可选；指定原字幕语言。未知时可先不传，或通过 Video Info 获取 |
| subtitles_translate_language | 可选；仅在业务明确需要翻译字幕时传入 |

## 5.3 标准输出

```json
{
  "job_id": "uuid",
  "status": "completed",
  "input_keywords": 2,
  "searches_succeeded": 2,
  "searches_failed": 0,
  "unique_videos": 17,
  "subtitles_succeeded": 12,
  "subtitles_unavailable": 4,
  "subtitles_failed": 1,
  "total_api_cost": 0.0,
  "results": [
    {
      "keyword": "animal hospital guide",
      "rank_group": 1,
      "rank_absolute": 1,
      "video": {
        "video_id": "example123",
        "title": "Animal Hospital Full Guide",
        "url": "https://www.youtube.com/watch?v=example123",
        "channel_name": "Example Channel",
        "views_count": 123456,
        "publication_date": "2026-07-01",
        "duration_seconds": 620
      },
      "subtitle": {
        "status": "available",
        "origin_language": "en",
        "translated_language": null,
        "segments_count": 142,
        "text": "Full normalized transcript..."
      }
    }
  ]
}
```

# 6. DataForSEO 调用规范

## 6.1 认证

DataForSEO 使用 HTTP Basic Authentication。用户名为 API login，密码为 API password。

```http
Authorization: Basic base64(login:password)
Content-Type: application/json
```

## 6.2 搜索请求

```http
POST https://api.dataforseo.com/v3/serp/youtube/organic/live/advanced

[
  {
    "keyword": "animal hospital guide",
    "location_code": 2840,
    "language_code": "en",
    "device": "desktop",
    "os": "windows",
    "block_depth": 20,
    "tag": "job_uuid:keyword_index"
  }
]
```

Live endpoint 每次仅提交一个任务最容易控制错误和成本。解析时不要假设 items 中全部是视频；只处理 type 等于 youtube_video 的项目，忽略频道、播放列表或其他 SERP block。

## 6.3 搜索结果解析
- 先检查顶层 status_code 是否为 20000。
- 再遍历 tasks，检查每个 task.status_code。
- 读取 tasks[0].result；result 可能为空。
- 遍历 result[*].items，仅保留 type == youtube_video。
- 至少保存 video_id、title、url、rank_group、rank_absolute。
- 其他字段采用容错读取，不得因字段缺失导致整个任务失败。
- 按 video_id 全局去重，但必须保留 keyword 与 video 的多对多排名关系。

## 6.4 字幕请求

```http
POST https://api.dataforseo.com/v3/serp/youtube/video_subtitles/live/advanced

[
  {
    "video_id": "example123",
    "location_code": 2840,
    "language_code": "en",
    "device": "desktop",
    "os": "windows",
    "subtitles_language": "en",
    "tag": "job_uuid:example123"
  }
]
```

字幕请求应针对去重后的 video_id 执行一次。若同一视频被多个关键词命中，不得重复计费调用。

## 6.5 字幕结果解析
- 检查 API 和 task 两层 status_code。
- 读取 result[0].unsupported_language、origin_language、translate_language、subtitles_count、items。
- 字幕状态分类为 available、unavailable、unsupported_language、api_error、parse_error。
- 保存所有原始 items，避免后续需要时间轴时再次付费。
- 完整字幕由字幕 items 的 text 字段按 rank_absolute 或开始时间顺序合并。
- 不得把 subtitles_count == 0 当作系统异常；它通常表示该视频无可获取字幕。

# 7. 字幕规范化算法

系统必须同时保存 raw_segments 和 normalized_text。原始分段是审计和重新处理的依据，normalized_text 用于搜索、关键词抽取和大模型分析。
- 按 rank_absolute 升序排序；若存在明确的开始时间字段，则以开始时间为主。
- 对每段 text 执行 Unicode 空白归一化，去除首尾空格。
- 过滤空文本，但不要删除音乐、掌声等标记，除非另有业务配置。
- 连续完全相同的字幕段仅保留一次。
- 对自动字幕可能出现的滚动重复，使用“前后词重叠”轻度去重；不得激进改写原文。
- 段落之间默认以单个空格连接；另提供保留时间轴的 JSON。
- 计算 transcript_sha256，便于检测重复或后续版本变化。

# 8. 数据库模型

| 表 | 关键字段 |
| --- | --- |
| jobs | id, status, request_json, started_at, completed_at, cost_total, error_summary |
| keyword_searches | id, job_id, keyword, location_code, language_code, status, api_cost, raw_response |
| videos | video_id PK, title, url, channel_id, channel_name, published_at, views_count, duration_seconds, metadata_json |
| keyword_videos | keyword_search_id, video_id, rank_group, rank_absolute, result_type |
| subtitle_tracks | id, video_id, requested_language, origin_language, translated_language, status, segment_count, normalized_text, sha256, api_cost, raw_response |
| subtitle_segments | subtitle_track_id, rank_absolute, start_time, end_time, duration, text |

videos.video_id 必须唯一；keyword_videos 使用复合唯一约束避免重复关系；subtitle_tracks 可按 (video_id, requested_language, translated_language) 建唯一索引，实现缓存和幂等。

# 9. 处理流程与状态机

```text
CREATED
  -> SEARCHING
  -> SEARCH_COMPLETED
  -> FETCHING_SUBTITLES
  -> COMPLETED

Any stage
  -> PARTIAL_COMPLETED
  -> FAILED
  -> CANCELLED
```

## 9.1 详细流程
- 创建 job，校验输入并计算最大可能请求数量。
- 逐关键词调用 Organic Live Advanced，立即保存原始响应和 cost。
- 提取 youtube_video，保存 keyword-video 关系。
- 全局按 video_id 去重，并应用 max_total_videos_per_job 安全上限。
- 查询本地字幕缓存；已有成功结果则不重复调用。
- 对剩余视频按受控并发调用 Video Subtitles Live Advanced。
- 每完成一个视频立即提交数据库，保证中断后可续跑。
- 汇总成功、无字幕、失败、API 成本，生成 JSON 或 CSV 导出。

# 10. 错误处理与重试

| 情况 | 处理 |
| --- | --- |
| HTTP 401/403 | 不重试；标记凭证或权限错误并停止作业 |
| HTTP 429 | 读取 Retry-After；指数退避并降低并发 |
| HTTP 5xx / 网络超时 | 指数退避重试，最多 MAX_RETRIES |
| 顶层 status_code 非 20000 | 按 DataForSEO 错误码分类；可重试错误进入重试队列 |
| task.status_code 非 20000 | 只失败当前任务，记录 task id、code 和 message |
| result 为空 | 记录 empty_result，不视为解析异常 |
| 无字幕或字幕数为 0 | 记录 unavailable，不重试 |
| unsupported_language=true | 记录 unsupported_language；可选尝试不传 subtitles_language 再请求一次 |
| JSON 字段变化或缺失 | 容错解析并保存 raw_response；记录 schema_warning |

重试必须具备抖动，例如 delay = min(cap, base * 2^attempt) + random_jitter。同一请求的重试不得产生数据库重复记录。

# 11. 成本控制
- 第一版默认 block_depth=20，max_videos_per_keyword=10。
- 字幕请求前必须按 video_id 去重并查询缓存。
- 从响应 task.cost 累加真实成本，不使用硬编码价格。
- 作业创建时支持 max_api_cost 可选上限；预计或累计成本超过上限时停止后续请求。
- 先完成全部搜索，再按排名和播放量选择要抓字幕的视频，可显著减少字幕调用次数。
- 保存失败类型；对明确无字幕的视频设置缓存有效期，避免短期内重复付费查询。

# 12. Python 参考实现骨架

```python
from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

BASE_URL = os.getenv("DATAFORSEO_BASE_URL", "https://api.dataforseo.com")
LOGIN = os.environ["DATAFORSEO_LOGIN"]
PASSWORD = os.environ["DATAFORSEO_PASSWORD"]

class DataForSEOError(RuntimeError):
    pass

class DataForSEOClient:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            base_url=BASE_URL,
            auth=(LOGIN, PASSWORD),
            timeout=httpx.Timeout(60.0, connect=10.0),
            headers={"Content-Type": "application/json"},
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def _post(self, path: str, payload: list[dict[str, Any]]) -> dict[str, Any]:
        response = await self.client.post(path, json=payload)
        response.raise_for_status()
        data = response.json()

        if data.get("status_code") != 20000:
            raise DataForSEOError(
                f'API error {data.get("status_code")}: {data.get("status_message")}'
            )
        return data

    async def search_youtube(
        self,
        keyword: str,
        *,
        location_code: int = 2840,
        language_code: str = "en",
        block_depth: int = 20,
    ) -> dict[str, Any]:
        payload = [{
            "keyword": keyword,
            "location_code": location_code,
            "language_code": language_code,
            "device": "desktop",
            "os": "windows",
            "block_depth": block_depth,
        }]
        return await self._post(
            "/v3/serp/youtube/organic/live/advanced",
            payload,
        )

    async def get_subtitles(
        self,
        video_id: str,
        *,
        location_code: int = 2840,
        language_code: str = "en",
        subtitles_language: str | None = None,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {
            "video_id": video_id,
            "location_code": location_code,
            "language_code": language_code,
            "device": "desktop",
            "os": "windows",
        }
        if subtitles_language:
            item["subtitles_language"] = subtitles_language

        return await self._post(
            "/v3/serp/youtube/video_subtitles/live/advanced",
            [item],
        )
```

## 12.1 搜索结果提取示例

```python
def extract_youtube_videos(response: dict[str, Any]) -> list[dict[str, Any]]:
    videos: list[dict[str, Any]] = []

    for task in response.get("tasks") or []:
        if task.get("status_code") != 20000:
            continue

        for result in task.get("result") or []:
            for item in result.get("items") or []:
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
                    "rank_group": item.get("rank_group"),
                    "rank_absolute": item.get("rank_absolute"),
                    "channel_id": item.get("channel_id"),
                    "channel_name": item.get("channel_name"),
                    "views_count": item.get("views_count"),
                    "publication_date": item.get("publication_date"),
                    "duration_seconds": (
                        item.get("duration_time_seconds")
                        or item.get("duration_time_second")
                    ),
                })
    return videos
```

## 12.2 字幕提取示例

```python
def extract_transcript(response: dict[str, Any]) -> dict[str, Any]:
    tasks = response.get("tasks") or []
    if not tasks:
        return {"status": "api_error", "segments": [], "text": ""}

    task = tasks[0]
    if task.get("status_code") != 20000:
        return {"status": "api_error", "segments": [], "text": ""}

    results = task.get("result") or []
    if not results:
        return {"status": "unavailable", "segments": [], "text": ""}

    result = results[0]
    if result.get("unsupported_language"):
        return {
            "status": "unsupported_language",
            "origin_language": result.get("origin_language"),
            "segments": [],
            "text": "",
        }

    segments = sorted(
        result.get("items") or [],
        key=lambda x: x.get("rank_absolute") or 0,
    )
    texts: list[str] = []
    previous = None

    for segment in segments:
        text = " ".join((segment.get("text") or "").split())
        if not text or text == previous:
            continue
        texts.append(text)
        previous = text

    status = "available" if texts else "unavailable"
    return {
        "status": status,
        "origin_language": result.get("origin_language"),
        "translated_language": result.get("translate_language"),
        "segments": segments,
        "text": " ".join(texts),
    }
```

# 13. API 或 CLI 服务设计

## 13.1 建议 HTTP API

| 接口 | 说明 |
| --- | --- |
| POST /jobs/youtube-transcripts | 创建关键词搜索和字幕采集作业 |
| GET /jobs/{job_id} | 查看进度、统计与错误 |
| GET /jobs/{job_id}/results | 分页获取视频和字幕结果 |
| POST /jobs/{job_id}/retry | 仅重试可重试失败项 |
| GET /videos/{video_id}/transcript | 读取已缓存字幕 |
| GET /health | 服务健康状态，不测试付费 API |

## 13.2 CLI 示例

```bash
python -m app collect   --keyword "animal hospital guide"   --keyword "animal hospital classes"   --location-code 2840   --language-code en   --max-videos 10   --subtitles-language en   --output results.json
```

# 14. 并发与限流
- 搜索和字幕使用独立 semaphore，默认搜索并发 3、字幕并发 5。
- 不要一次性创建数万个协程；使用有界队列。
- HTTP 客户端全局复用连接池，不得每个视频新建客户端。
- 遇到 429 或连续 5xx 时动态降低并发。
- 作业取消时停止创建新请求，但允许正在执行的请求完成并保存结果。

# 15. 可观测性
- 日志字段：job_id、keyword、video_id、endpoint、attempt、status_code、task_status_code、latency_ms、cost。
- 指标：请求数、成功率、429 数量、平均延迟、字幕可用率、每作业成本、缓存命中率。
- 不要记录 Authorization header、API password 或完整凭证。
- 保存 DataForSEO task id 仅用于故障排查，不向普通终端用户展示。

# 16. 测试计划

| 测试类型 | 必须覆盖 |
| --- | --- |
| 单元测试 | 字段缺失、空 result、非视频 item、重复 video_id、空字幕、重复字幕段 |
| HTTP 模拟测试 | 20000 成功、401、429、500、超时、task 层错误 |
| 集成测试 | 使用单个低成本关键词，限制 block_depth 和视频数 |
| 幂等测试 | 相同作业重跑不得重复请求已缓存字幕或产生重复数据库行 |
| 成本测试 | 响应中的 cost 能准确累计；超过 max_api_cost 后停止 |
| 恢复测试 | 进程在字幕阶段中断后可从未完成 video_id 继续 |

# 17. 验收标准
- 输入一个有效关键词后，系统能够返回至少搜索结果中可用的视频 title、url 和 video_id。
- 仅解析 youtube_video 类型，其他 SERP 项不会导致异常。
- 同一 video_id 被多个关键词命中时只调用一次字幕接口。
- 有字幕的视频能够保存分段字幕和合并文本。
- 无字幕视频被正确标记 unavailable，而不是无限重试。
- 所有 API 调用均记录 task cost 并汇总到 job。
- 网络临时错误可自动重试，认证错误立即停止。
- 凭证不出现在源代码、日志、返回 JSON 和测试快照中。
- 作业可以断点续跑并保持数据库幂等。
- 可导出 UTF-8 JSON，字段结构符合本文档定义。

# 18. 给开发 AI 的执行指令

请严格按照本文档实现一个可运行的 Python 项目。先完成最小可用版本：CLI + SQLite + 异步 httpx，再将存储层设计为可替换 PostgreSQL。必须提供 README、.env.example、类型标注、pytest 测试、数据库迁移或初始化脚本、结构化日志和示例输出。不得使用 yt-dlp，不得直接请求 YouTube。
- 实现 DataForSEOClient，并把所有 API 字段访问写成容错解析。
- 实现 search -> normalize -> deduplicate -> subtitles -> persist 的完整流程。
- 实现缓存、重试、并发限制、最大成本和最大视频数量保护。
- 所有外部 HTTP 调用必须可以在测试中 mock。
- 代码完成后运行格式化、类型检查和测试，并修复全部失败。
- README 中明确注明无字幕视频不会自动语音转写。

# 19. 官方资料

YouTube Organic Live Advanced: https://docs.dataforseo.com/v3/serp/youtube/organic/live/advanced/

YouTube Video Subtitles Live Advanced: https://docs.dataforseo.com/v3/serp/youtube/video_subtitles/live/advanced/

YouTube Video Info: https://docs.dataforseo.com/v3/serp/youtube/video_info/task_post/

说明：接口字段和价格可能调整。开发与上线前，应再次以 DataForSEO 官方文档及账户 Pricing 页面为准。