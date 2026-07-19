"""
YouTube 搜索和提取模块

搜索和字幕均通过 DataForSEO SERP API 获取，不再依赖 yt-dlp 或代理 IP。
"""

import asyncio
import re
from typing import List, Dict, Tuple

from .config import Config
from .models import YouTubeItem
from .utils import format_duration, load_cache, save_cache, build_disambiguated_query
from .dataforseo_client import DataForSEOClient, DataForSEOError, extract_youtube_videos, extract_transcript


class YouTube:
    """YouTube 搜索和提取（支持并行）"""

    def __init__(self):
        self.config = Config
        self.client = DataForSEOClient()

    async def search_batch(self, keywords: List[str], filter_keyword: str = '') -> Dict[str, List[YouTubeItem]]:
        """
        并行搜索多个关键词（带实时进度反馈）

        Args:
            keywords: 关键词列表
            filter_keyword: 过滤词，用于过滤不相关视频（可选）

        Returns:
            {keyword: [YouTubeItem, ...]}
        """
        print(f"\n🔍 YouTube 搜索: {len(keywords)} 个关键词")
        if filter_keyword:
            print(f"   过滤词: \"{filter_keyword}\"")

        # 每次运行清空上一次的过滤日志，避免和本次结果混淆
        self._clear_filter_log("youtube")

        # 创建信号量限制并发数
        semaphore = asyncio.Semaphore(self.config.YOUTUBE_SEARCH_WORKERS)

        # 包装函数：搜索并返回 (keyword, result, error, retry_count)
        async def search_and_tag(keyword: str, index: int, total: int):
            retry_count = 0
            async with semaphore:
                # 开始搜索时立即打印
                print(f"  🔄 [{index}/{total}] 开始搜索: {keyword}")

                for attempt in range(self.config.YOUTUBE_RETRIES):
                    try:
                        # 使用 DataForSEO 搜索（传入 filter_keyword 优化查询）
                        videos = await self._dataforseo_search(keyword, filter_keyword=filter_keyword)

                        # 过滤时长
                        filtered = self._filter_by_duration(videos)

                        # 按过滤词过滤
                        if filter_keyword:
                            filtered = self._filter_by_keyword(filtered, filter_keyword)

                        # 转换为 YouTubeItem
                        items = [self._to_item(v) for v in filtered]

                        return (keyword, items, None, retry_count)

                    except DataForSEOError as e:
                        # 认证/权限错误，重试没用，直接失败
                        return (keyword, [], e, retry_count)

                    except Exception as e:
                        retry_count = attempt + 1
                        if attempt == self.config.YOUTUBE_RETRIES - 1:
                            return (keyword, [], e, retry_count)
                        await asyncio.sleep(2 ** attempt)

        # 创建所有任务
        tasks = [search_and_tag(kw, i+1, len(keywords)) for i, kw in enumerate(keywords)]

        # 实时处理完成的任务
        result_dict = {}
        completed = 0
        total = len(keywords)

        for coro in asyncio.as_completed(tasks):
            keyword, result, error, retry_count = await coro
            completed += 1

            if error:
                retry_info = f" (重试 {retry_count} 次)" if retry_count > 0 else ""
                print(f"  ✗ [{completed}/{total}] {keyword}: {error}{retry_info}")
                result_dict[keyword] = []
            else:
                retry_info = f" (重试 {retry_count} 次)" if retry_count > 0 else ""
                print(f"  ✓ [{completed}/{total}] {keyword}: {len(result)} 个视频{retry_info}")
                result_dict[keyword] = result

        return result_dict

    async def _search_single(self, keyword: str, semaphore, filter_keyword: str = '') -> List[YouTubeItem]:
        """
        搜索单个关键词

        Args:
            keyword: 关键词
            semaphore: 并发控制信号量
            filter_keyword: 过滤词，用于过滤不相关视频

        Returns:
            YouTubeItem 列表
        """
        async with semaphore:
            for attempt in range(self.config.YOUTUBE_RETRIES):
                try:
                    # 使用 DataForSEO 搜索（传入 filter_keyword 优化查询）
                    videos = await self._dataforseo_search(keyword, filter_keyword=filter_keyword)

                    # 过滤时长
                    filtered = self._filter_by_duration(videos)

                    # 按过滤词过滤
                    if filter_keyword:
                        filtered = self._filter_by_keyword(filtered, filter_keyword)

                    # 转换为 YouTubeItem
                    items = [self._to_item(v) for v in filtered]

                    return items

                except DataForSEOError as e:
                    raise Exception(f"搜索失败: {e}")

                except Exception as e:
                    if attempt == self.config.YOUTUBE_RETRIES - 1:
                        raise Exception(f"搜索失败: {e}")
                    await asyncio.sleep(2 ** attempt)

    async def _dataforseo_search(self, keyword: str, filter_keyword: str = '') -> List[Dict]:
        """
        使用 DataForSEO YouTube Organic Live Advanced 搜索视频

        Args:
            keyword: 关键词
            filter_keyword: 过滤词（可选，用于给搜索 query 加消歧词）

        Returns:
            视频信息列表
        """
        # query 本身带上消歧词（如 "roblox"），让 YouTube 自己的搜索排序做
        # 消歧，而不是只在结果出来后靠标题过滤——过滤只能从已经搜到的结果里
        # 挑，搜索引擎排序阶段已经把大量撞名的现实世界内容排在前面了，过滤
        # 救不回来
        search_keyword = build_disambiguated_query(keyword, filter_keyword)

        response = await self.client.search_youtube(search_keyword)
        videos = extract_youtube_videos(response)

        if not videos:
            raise Exception("未找到任何视频")

        return videos

    def _duration_seconds(self, video: Dict) -> float:
        duration = video.get('duration_seconds')
        if duration is None:
            return float('inf')
        return duration

    def _filter_by_duration(self, videos: List[Dict]) -> List[Dict]:
        """
        根据时长过滤视频

        Args:
            videos: 视频列表

        Returns:
            过滤后的视频列表
        """
        if not videos:
            return []

        # 过滤掉超过最大时长的视频
        filtered = [
            v for v in videos
            if self._duration_seconds(v) <= self.config.YOUTUBE_MAX_DURATION
        ]

        # 如果过滤后有视频，返回所有过滤后的视频（不限制数量）
        if filtered:
            return filtered

        # 如果所有视频都超时长，返回时长最短的 1 个
        sorted_by_duration = sorted(
            videos,
            key=self._duration_seconds
        )
        return sorted_by_duration[:1]

    # 过滤词里这些词不带辨识度（几乎每个 Roblox 游戏标题都有），
    # 用来判断相关性时忽略掉，避免"必须完整匹配整个短语"的过严过滤
    _GENERIC_FILTER_WORDS = {"roblox", "game", "games", "the", "a", "an", "of", "in", "on", "and", "for"}

    def _significant_words(self, filter_keyword: str) -> List[str]:
        """从过滤词里提取有辨识度的词（去掉通用词和过短的词）"""
        words = [w for w in re.findall(r"[a-z0-9]+", filter_keyword.lower()) if len(w) >= 3]
        significant = [w for w in words if w not in self._GENERIC_FILTER_WORDS]
        return significant or words

    def _filter_by_keyword(self, videos: List[Dict], filter_keyword: str) -> List[Dict]:
        """
        按过滤词过滤视频标题，丢弃明显不相关的视频

        只要标题命中过滤词里任意一个有辨识度的词就保留（而不是要求完整短语
        逐字匹配）——游戏视频标题措辞五花八门（词序不同、缺字、加符号等），
        要求完整短语匹配会把大量真实相关的内容也过滤掉。宁可漏过滤（保留一两个
        不相关结果），也不要错杀相关内容。

        Args:
            videos: 视频列表
            filter_keyword: 过滤词（如 "Roblox Animal Hospital"）

        Returns:
            过滤后的视频列表
        """
        if not filter_keyword or not videos:
            return videos

        words = self._significant_words(filter_keyword)
        if not words:
            return videos

        kept = []
        filtered_out = []

        for v in videos:
            title = v.get('title', '')
            title_lower = title.lower()
            if any(re.search(rf"\b{re.escape(w)}\b", title_lower) for w in words):
                kept.append(v)
            else:
                filtered_out.append(v)
                print(f"    🗑️ 过滤: \"{title[:60]}\" (不含 \"{filter_keyword}\" 任何关键词)")

        if not kept:
            print(f"    ⚠️ 所有视频均不含 \"{filter_keyword}\"，无相关视频")

        # 记录被过滤掉的视频到日志文件
        if filtered_out:
            self._log_filtered(filter_keyword, filtered_out, source="youtube")

        return kept

    def _clear_filter_log(self, source: str = "youtube"):
        """清空本次运行的过滤日志，确保每次运行都是全新的日志"""
        from pathlib import Path

        log_dir = Path(Config.DATA_DIR) / "out" / "filter_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"filtered_{source}.jsonl"
        log_file.write_text("", encoding="utf-8")

    def _log_filtered(self, filter_keyword: str, items: list, source: str = "unknown"):
        """记录被过滤掉的条目到日志文件，便于后期审查"""
        import os
        from pathlib import Path

        log_dir = Path(Config.DATA_DIR) / "out" / "filter_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"filtered_{source}.jsonl"

        entry = {
            "filter_keyword": filter_keyword,
            "source": source,
            "filtered_count": len(items),
            "items": [{"title": v.get("title", ""), "url": v.get("url", "")} for v in items]
        }

        with open(log_file, "a", encoding="utf-8") as f:
            import json
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _to_item(self, video: Dict) -> YouTubeItem:
        """
        转换为 YouTubeItem

        Args:
            video: 视频信息字典

        Returns:
            YouTubeItem 对象
        """
        duration_seconds = video.get('duration_seconds', 0) or 0
        return YouTubeItem(
            title=video.get('title', ''),
            url=video.get('url', ''),
            video_id=video.get('video_id', ''),
            channel=video.get('channel', ''),
            duration=format_duration(duration_seconds),
            duration_seconds=duration_seconds,
            view_count=video.get('view_count', 0),
            selected=True
        )

    async def extract_batch(self, items: List[YouTubeItem]) -> List[Tuple[YouTubeItem, str]]:
        """
        并行提取多个视频字幕

        Args:
            items: YouTubeItem 列表

        Returns:
            [(item, content), ...]
        """
        print(f"\n📥 YouTube 提取: {len(items)} 个视频")

        # 创建信号量限制并发数
        semaphore = asyncio.Semaphore(self.config.YOUTUBE_EXTRACT_WORKERS)

        # 并行提取
        tasks = [self._extract_single(item, semaphore) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计成功和失败
        success_count = sum(1 for _, content in results if content and not isinstance(content, Exception))
        failed_count = len(items) - success_count

        print(f"  ✓ 成功: {success_count}/{len(items)}")

        # 显示失败统计
        if failed_count > 0:
            print(f"  ✗ 失败: {failed_count}/{len(items)}")
            failed_items = [(item, content) for item, content in results if not content or isinstance(content, Exception)]
            if failed_items and failed_count <= 10:
                # 如果失败数量不多，列出所有失败项
                for item, _ in failed_items:
                    print(f"    - {item.video_id}: {item.title[:50]}...")
            elif failed_items:
                # 失败太多，只显示前5个
                print(f"    显示前5个失败项:")
                for item, _ in failed_items[:5]:
                    print(f"    - {item.video_id}: {item.title[:50]}...")

        return results

    async def _extract_single(self, item: YouTubeItem, semaphore) -> Tuple[YouTubeItem, str]:
        """
        提取单个视频字幕（带缓存）

        Args:
            item: YouTubeItem 对象
            semaphore: 并发控制信号量

        Returns:
            (item, content) 元组
        """
        async with semaphore:
            # 1. 检查缓存
            cache_data = load_cache(item.video_id, "youtube", title=item.title)
            if cache_data and cache_data.get("content"):
                print(f"  💾 缓存命中: {item.title[:50]}...")
                return (item, cache_data["content"])

            # 2. 缓存未命中，提取内容
            for attempt in range(self.config.YOUTUBE_RETRIES):
                try:
                    content = await self._get_transcript(item.video_id)

                    # 3. 保存到缓存（仅当确实拿到字幕时才缓存；"无字幕"不缓存，
                    # 因为供应商可能后续补充字幕，值得下次重新查询）
                    if content:
                        save_cache(item.video_id, "youtube", {
                            "title": item.title,
                            "url": item.url,
                            "video_id": item.video_id,
                            "content": content,
                            "source_type": "youtube"
                        }, title=item.title)

                    return (item, content)

                except DataForSEOError as e:
                    # 认证/权限错误，重试没用
                    print(f"    ✗ {item.video_id}: {e}")
                    return (item, "")

                except Exception as e:
                    if attempt == self.config.YOUTUBE_RETRIES - 1:
                        # 最后一次重试失败，记录并返回空内容
                        print(f"    ✗ {item.video_id}: 重试{self.config.YOUTUBE_RETRIES}次后失败: {e}")
                        return (item, "")
                    await asyncio.sleep(2 ** attempt)

    async def _get_transcript(self, video_id: str) -> str:
        """
        通过 DataForSEO Video Subtitles Live Advanced 获取字幕

        Args:
            video_id: 视频 ID

        Returns:
            字幕文本；无字幕/不支持语言时返回空字符串（非异常）
        """
        response = await self.client.get_subtitles(video_id)
        result = extract_transcript(response)

        status = result["status"]
        if status == "available":
            return result["text"]
        if status in ("unavailable", "unsupported_language"):
            # 该视频确实没有可用字幕，不是错误，不重试
            print(f"    ⚠️ {video_id}: 无可用字幕 ({status})")
            return ""

        # status == "api_error"：交给上层重试逻辑
        raise Exception(f"字幕接口返回异常: {response.get('status_message', 'unknown')}")

