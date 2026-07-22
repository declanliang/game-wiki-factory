"""
Web 搜索和提取模块

支持并行搜索和内容提取
"""

import asyncio
import aiohttp
import time
from typing import List, Dict, Tuple
from urllib.parse import urlparse

from .config import Config
from .models import WebItem
from .utils import is_blocked_domain, load_cache, save_cache, get_url_hash, build_disambiguated_query
from .cleaner import ContentCleaner


class TokenBucket:
    """Token Bucket 速率限制器"""

    def __init__(self, rpm: int):
        """
        初始化速率限制器

        Args:
            rpm: 每分钟请求数
        """
        self.rpm = rpm
        self.tokens = rpm
        self.last_update = time.time()
        self.lock = asyncio.Lock()

    async def acquire(self):
        """获取令牌（阻塞直到有令牌可用）"""
        async with self.lock:
            while self.tokens < 1:
                await asyncio.sleep(0.1)
                self._refill()
            self.tokens -= 1

    def _refill(self):
        """补充令牌"""
        now = time.time()
        elapsed = now - self.last_update

        # 每秒补充 rpm/60 个令牌
        self.tokens = min(self.rpm, self.tokens + elapsed * (self.rpm / 60))
        self.last_update = now


class Web:
    """Web 搜索和提取（支持并行）"""

    def __init__(self):
        self.config = Config
        self.cleaner = ContentCleaner()  # 初始化内容清理器
        self._serper_index = 0
        self._jina_index = 0
        self._key_lock = asyncio.Lock()

    async def _next_key(self, kind: str) -> Tuple[int, str]:
        keys = list(getattr(self.config, f"{kind}_API_KEYS", []))
        if not keys:
            return (0, "")
        async with self._key_lock:
            attribute = f"_{kind.casefold()}_index"
            index = getattr(self, attribute) % len(keys)
            setattr(self, attribute, index + 1)
        return (index + 1, keys[index])

    async def search_batch(self, keywords: List[str], filter_keyword: str = '') -> Dict[str, List[WebItem]]:
        """
        并行搜索多个关键词

        Args:
            keywords: 关键词列表
            filter_keyword: 过滤词，用于过滤不相关结果（可选）

        Returns:
            {keyword: [WebItem, ...]}
        """
        print(f"\n🔍 Web 搜索: {len(keywords)} 个关键词")

        # 创建信号量限制并发
        semaphore = asyncio.Semaphore(self.config.WEB_SEARCH_CONCURRENCY)

        # 并行搜索（带并发控制）
        tasks = [self._search_single(kw, semaphore, filter_keyword) for kw in keywords]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 构建结果字典
        result_dict = {}
        for keyword, result in zip(keywords, results):
            if isinstance(result, Exception):
                print(f"  ✗ {keyword}: {result}")
                result_dict[keyword] = []
            else:
                result_dict[keyword] = result
                print(f"  ✓ {keyword}: {len(result)} 个页面")

        return result_dict

    async def _search_single(self, keyword: str, semaphore, filter_keyword: str = '') -> List[WebItem]:
        """
        搜索单个关键词

        Args:
            keyword: 关键词
            semaphore: 并发控制信号量

        Returns:
            WebItem 列表
        """
        async with semaphore:
            # 添加小延迟避免触发速率限制
            await asyncio.sleep(0.3)

            try:
                # 调用 Serper API
                # 搜索 query 本身带上消歧词（如 "roblox"），而不是只在结果出来
                # 后做过滤——这样 Google 自己的相关性排序就能把撞名的现实世界
                # 内容排开，不需要事后从矮子里拔将军
                url = "https://google.serper.dev/search"
                search_query = build_disambiguated_query(keyword, filter_keyword)
                payload = {
                    "q": search_query,
                    "num": self.config.WEB_SEARCH_TOP_N
                }

                keys = list(getattr(self.config, "SERPER_API_KEYS", []))
                last_status = 0
                data = None
                for _ in range(max(1, len(keys))):
                    slot, key = await self._next_key("SERPER")
                    headers = {"X-API-KEY": key, "Content-Type": "application/json"}
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, json=payload, headers=headers, timeout=30) as response:
                            last_status = response.status
                            if response.status == 200:
                                data = await response.json()
                                break
                            if response.status not in {402, 403, 429}:
                                break
                            print(f"  ↻ Serper keySlot={slot} unavailable ({response.status}); trying next slot")
                if data is None:
                    raise Exception(f"Serper API 返回错误: {last_status}")
                results = data.get("organic", [])

                # 过滤屏蔽域名
                # 不再按 filter_keyword 过滤标题/摘要：Serper 关键词本身已经是
                # "游戏名 + 具体子主题"（如 "animal hospital codes"），搜索结果
                # 本身已经足够相关，再做子串过滤只会误伤措辞不同的合法结果。
                filtered = [
                    r for r in results
                    if not is_blocked_domain(r.get('link', ''), self.config.BLOCKED_DOMAINS)
                ]

                # 转换为 WebItem
                items = []
                for r in filtered[:self.config.WEB_SEARCH_TOP_N]:
                    domain = urlparse(r.get('link', '')).netloc
                    items.append(WebItem(
                        title=r.get('title', ''),
                        url=r.get('link', ''),
                        domain=domain,
                        snippet=r.get('snippet', ''),
                        selected=True
                    ))

                return items

            except Exception as e:
                raise Exception(f"搜索失败: {e}")

    async def extract_batch(self, items: List[WebItem]) -> List[Tuple[WebItem, str]]:
        """
        并行提取多个页面内容

        Args:
            items: WebItem 列表

        Returns:
            [(item, content), ...]
        """
        print(f"\n📥 Web 提取: {len(items)} 个页面")

        # 创建信号量和速率限制器
        semaphore = asyncio.Semaphore(self.config.JINA_CONCURRENCY)
        rate_limiter = TokenBucket(self.config.JINA_RPM)

        # 并行提取
        tasks = [self._extract_single(item, semaphore, rate_limiter) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计成功和失败
        success_count = sum(1 for _, content in results if content and not isinstance(content, Exception))
        print(f"  ✓ 成功: {success_count}/{len(items)}")

        return results

    async def _extract_single(self, item: WebItem, semaphore, rate_limiter) -> Tuple[WebItem, str]:
        """
        提取单个页面内容（带缓存和重试）

        Args:
            item: WebItem 对象
            semaphore: 并发控制信号量
            rate_limiter: 速率限制器

        Returns:
            (item, content) 元组
        """
        async with semaphore:
            # 1. 检查缓存
            url_hash = get_url_hash(item.url)
            cache_data = load_cache(url_hash, "web", title=item.title)
            if cache_data and cache_data.get("content"):
                print(f"  💾 缓存命中: {item.title[:50]}...")
                return (item, cache_data["content"])

            # 2. 缓存未命中，提取内容（带重试）
            for attempt in range(self.config.WEB_EXTRACT_RETRIES):
                # 速率限制
                await rate_limiter.acquire()

                try:
                    # 使用 Jina Reader
                    jina_url = f"https://r.jina.ai/{item.url}"
                    slot, key = await self._next_key("JINA")
                    headers = {"Authorization": f"Bearer {key}"} if key else {}

                    async with aiohttp.ClientSession() as session:
                        async with session.get(jina_url, headers=headers, timeout=30) as response:
                            # HTTP 错误处理
                            if response.status != 200:
                                if response.status in {402, 403, 429}:
                                    print(f"  ↻ Jina keySlot={slot} unavailable ({response.status}); trying next slot")
                                if attempt < self.config.WEB_EXTRACT_RETRIES - 1:
                                    await asyncio.sleep(2 ** attempt)  # 指数退避：2s, 4s, 8s
                                    continue
                                return (item, "")

                            content = await response.text()

                            # 内容长度检查
                            if len(content.strip()) < 500:
                                if attempt < self.config.WEB_EXTRACT_RETRIES - 1:
                                    await asyncio.sleep(2 ** attempt)
                                    continue
                                return (item, "")

                            # 清理内容（移除导航链接、广告等）
                            cleaned_content = self.cleaner.clean(content)

                            # 3. 保存到缓存
                            save_cache(url_hash, "web", {
                                "title": item.title,
                                "url": item.url,
                                "domain": item.domain,
                                "content": cleaned_content,  # 保存清理后的内容
                                "source_type": "web"
                            }, title=item.title)

                            return (item, cleaned_content)

                except Exception as e:
                    if attempt == self.config.WEB_EXTRACT_RETRIES - 1:
                        # 最后一次重试失败，返回空内容
                        return (item, "")
                    await asyncio.sleep(2 ** attempt)  # 指数退避

            return (item, "")

