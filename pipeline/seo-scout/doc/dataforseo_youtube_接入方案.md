# DataForSEO 接入方案 — 替换 YouTube 的 yt-dlp + 代理 IP

版本：1.0
日期：2026-07-15
范围：仅 `seoscout/core/youtube.py`（YouTube 搜索 + 字幕提取）。Web 搜索（Serper）/ 提取（Jina）的代理逻辑本次不改动。

## 1. 背景与目标

当前 YouTube 搜索用 `yt-dlp` 子进程，字幕提取用 `youtube_transcript_api`，两者都需要代理 IP 才能绕开 YouTube 的 IP 封锁，且代理本身不稳定（本次真实项目测试中代理提供商本身连不上，本地不走代理又被 `RequestBlocked`）。

目标：改用 DataForSEO 的两个官方 SERP API（`youtube/organic/live/advanced` 搜索、`youtube/video_subtitles/live/advanced` 取字幕），不再自己维护代理/Cookie/IP 池，把这部分不稳定性转嫁给 DataForSEO。

参考文档：`doc/使用dataforseo获取youtube数据`（供应商提供的完整技术规格，面向独立服务设计，含数据库/任务队列/HTTP API）。**本方案只取其中与我们项目相关的部分**，不引入数据库、任务状态机、HTTP API、Celery——这些在 `使用dataforseo获取youtube数据` 里是为一个独立微服务设计的，seoscout 是单机 CLI + JSON 文件 + 本地磁盘缓存，用不上。

## 2. 不变的部分（接口边界）

`seoscout/core/youtube.py` 对外只暴露两个方法，本次改造保持签名不变，因此 `search.py`、`collect.py`、`cli.py` 全部零改动：

```python
async def search_batch(keywords: List[str], filter_keyword: str = '') -> Dict[str, List[YouTubeItem]]
async def extract_batch(items: List[YouTubeItem]) -> List[Tuple[YouTubeItem, str]]
```

`YouTubeItem`（`core/models.py`）字段不变：`title, url, video_id, channel, duration, duration_seconds, view_count, selected`。

已有的关键词相关性过滤逻辑（`_filter_by_keyword`、`_filter_by_duration`、`_clear_filter_log`、`_log_filtered`）不变——这些是基于标题文本做的过滤，与视频数据的获取方式（yt-dlp 还是 DataForSEO）无关。

已有的本地磁盘缓存（`utils.load_cache`/`save_cache`，按 `video_id` 缓存字幕内容）不变，天然满足供应商文档里"字幕请求前必须按 video_id 去重查缓存，避免重复计费"的要求，不需要额外建数据库。

## 3. 改动的部分

### 3.1 新增 `seoscout/core/dataforseo_client.py`

一个薄封装，用项目已有的 `aiohttp`（不引入 `httpx`），HTTP Basic Auth。

```python
class DataForSEOClient:
    async def search_youtube(self, keyword, *, location_code, language_code, device, os_name, block_depth) -> dict
    async def get_subtitles(self, video_id, *, location_code, language_code, subtitles_language=None) -> dict
```

- `_post()` 内部方法：POST 请求 + 双层 `status_code` 容错解析（先查顶层 `status_code == 20000`，再查 `tasks[0].status_code`）。
- 错误分类按供应商文档第 10 节：401/403 不重试直接抛出（凭证问题，重试没用）；429 读 `Retry-After` 退避；5xx / 超时按指数退避重试 `Config.YOUTUBE_RETRIES` 次。
- 每次响应尝试读取 `tasks[0].cost`，累加到一个进程内计数器（不落库），跑完一批打印总花费，类似 `LLMClient.print_stats()`。

### 3.2 改写 `search_batch()` 内部（原来调 `_ytdlp_search`）

- 用 `dataforseo_client.search_youtube(search_keyword, block_depth=Config.YOUTUBE_BLOCK_DEPTH)` 替代 yt-dlp 子进程调用。
- 保留现有"连写优先→大写引号回退"的关键词优化逻辑（这是搜索相关性技巧，和数据源无关）——但把默认回退行为改为更保守：因为每次调用都计费，无结果时才回退，不做多轮 `ytsearchN` 递增查询（DataForSEO 一次 `block_depth` 请求就能拿到足够候选，不像 yt-dlp 那样需要分批加量）。
- 解析响应：只处理 `item.type == "youtube_video"`，其余字段容错读取（缺字段不整体失败），按供应商文档 12.1 示例。
- 字段映射到 `YouTubeItem`：
  | YouTubeItem 字段 | DataForSEO 字段 |
  |---|---|
  | title | title |
  | url | url |
  | video_id | video_id |
  | channel | channel_name |
  | view_count | views_count |
  | duration_seconds | duration_time_seconds |
  | duration | 用已有的 `utils.format_duration(duration_seconds)` 自己格式化（DataForSEO 不直接给字符串） |

- 后续 `_filter_by_duration`、`_filter_by_keyword`、`_to_item` 全部复用，仅 `_to_item` 内部字段读取要跟着改。

### 3.3 改写 `extract_batch()` / `_extract_single()` 内部（原来调 `_get_transcript`，用 `youtube_transcript_api`）

- 缓存检查逻辑不变（`load_cache` 命中直接返回）。
- 缓存未命中时调用 `dataforseo_client.get_subtitles(video_id)`。
- 解析按供应商文档 12.2：
  - `result[0].unsupported_language == true` → 标记不可用，不重试，返回空字符串（不是异常，是正常业务状态）。
  - `items` 按 `rank_absolute` 排序，逐段做 Unicode 空白归一化 + 连续完全重复段去重，拼接成 `normalized_text`。
  - `subtitles_count == 0` 或 `result` 为空 → 视为"该视频无字幕"，不算系统异常，不重试。
- 去掉原来 `_get_transcript()` 里的所有 IP 轮换重试逻辑（`unique_tag`/`channel-` 替换那段）——不再需要。
- 去掉中文/英文语言优先级尝试逻辑的意义变了：`get_subtitles` 支持传 `subtitles_language` 精确指定；可以先不传（拿视频原始语言字幕），非必需再扩展到多语言尝试（见"暂不做"）。

### 3.4 Config 新增项（`seoscout/core/config.py` + `.env`）

```
DATAFORSEO_LOGIN=
DATAFORSEO_PASSWORD=
DATAFORSEO_BASE_URL=https://api.dataforseo.com
YOUTUBE_LOCATION_CODE=2840
YOUTUBE_LANGUAGE_CODE=en
YOUTUBE_DEVICE=desktop
YOUTUBE_OS=windows
YOUTUBE_BLOCK_DEPTH=10
```

`YOUTUBE_SEARCH_WORKERS`/`YOUTUBE_EXTRACT_WORKERS`（现有并发配置）沿用，但把默认值从 10/15 调低为供应商建议的 3/5——DataForSEO 账号大概率有并发上限，且并发越高单位时间花费越集中，出错了不好排查。`block_depth` 默认给 10 而不是文档建议的 20：因为 `collect.py` 本来就只取每个关键词 Top-1（`YOUTUBE_EXTRACT_TOP_K=1`）去提字幕，搜索阶段拿太多候选没有意义，只是白花钱。

不新增数据库配置、不新增 `max_api_cost` 硬熔断（先打印花费观察实际成本，成本明显后再决定要不要加熔断）。

### 3.5 依赖清理（`pyproject.toml`）

移除 `youtube-transcript-api`、`requests`（`requests` 目前只在 `youtube.py` 里为代理 session 用，删掉后确认没有其他地方用到再移除；`web.py`/`aiohttp` 生态不受影响）。yt-dlp 本来就不是声明依赖（用户手动装的），无需处理。

## 4. 明确不做的事（避免过度设计）

- 不引入 Postgres/SQLAlchemy/Celery/HTTP API/任务状态机——继续用现成的 JSON 文件 + 本地磁盘缓存。
- 不做 `max_api_cost` 硬性熔断——先跑通看实际花费再说。
- 不做字幕多语言 fallback 链（原来 `_get_transcript` 里"中文→英文→任意语言"三级尝试）——先用默认（不传 `subtitles_language`，拿视频原始语言），后续如果发现语言不对再加。
- Web（Serper + Jina）阶段的代理逻辑不动，`Config.get_proxy_url_for_stage()`、`.env` 里的 `TUNNEL_*`/`USE_PROXY*` 全部保留原样。

## 5. 验证计划

1. 单独跑 `_ytdlp_search` 的替代函数，对一个已知关键词（如 "roblox animal hospital codes"）验证能拿到 video_id/title/url。
2. 对拿到的 video_id 跑字幕提取，验证 `unavailable`（无字幕）和 `available`（有字幕）两种情况都不报异常。
3. 用 `projects/animal_hospital/keywords.json` 里之前 7 个 YouTube 全部 `RequestBlocked` 的关键词跑一次完整 `search` + `collect`，确认能拿到视频和字幕，并观察日志里打印的实际花费。
4. 确认 `search_results.json`/`collected/*.json` 的字段结构和之前完全一致（因为 `YouTubeItem` 没变，下游 `generate`/`translate` 不需要跟着改）。
