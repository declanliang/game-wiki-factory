from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

from .util import cache_key, dump_json, load_json, utc_now


class HttpError(RuntimeError):
    pass


class CachedHttpClient:
    def __init__(self, cache_dir: Path, timeout: int = 45, refresh: bool = False):
        self.cache_dir = cache_dir / "http"
        self.timeout = timeout
        self.refresh = refresh
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "gamewiki-automation/0.1 (+local research tool)"})

    def get(self, url: str, *, ttl: int = 3600, headers: dict[str, str] | None = None) -> requests.Response:
        key = cache_key("GET", url)
        cached = self.cache_dir / f"{key}.json"
        if not self.refresh and cached.exists() and time.time() - cached.stat().st_mtime < ttl:
            item = load_json(cached)
            response = requests.Response()
            response.status_code = item["status"]
            response.url = url
            response._content = item["body"].encode("utf-8")
            response.headers.update(item.get("headers", {}))
            response.encoding = "utf-8"
            return response
        response = self._request("GET", url, headers=headers)
        content_type = response.headers.get("content-type", "")
        if "text" in content_type or "json" in content_type or not content_type:
            dump_json(cached, {
                "status": response.status_code,
                "body": response.text,
                "headers": {"content-type": content_type},
                "retrievedAt": utc_now(),
            })
        return response

    def get_json(self, url: str, *, ttl: int = 3600) -> Any:
        response = self.get(url, ttl=ttl, headers={"Accept": "application/json"})
        if response.status_code >= 400:
            raise HttpError(f"GET {url} returned HTTP {response.status_code}: {response.text[:300]}")
        return response.json()

    def post_json(self, url: str, payload: Any, headers: dict[str, str], *, timeout: int | None = None) -> Any:
        response = self._request("POST", url, json=payload, headers=headers, timeout=timeout)
        if response.status_code >= 400:
            raise HttpError(f"POST {url} returned HTTP {response.status_code}: {response.text[:1000]}")
        if not response.content:
            raise HttpError(f"POST {url} returned an empty response")
        return response.json()

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        timeout = kwargs.pop("timeout", None) or self.timeout
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.session.request(method, url, timeout=timeout, **kwargs)
                if response.status_code not in {429, 500, 502, 503, 504}:
                    return response
                last_error = HttpError(f"temporary HTTP {response.status_code}")
            except requests.RequestException as exc:
                last_error = exc
            if attempt < 2:
                time.sleep(2**attempt)
        raise HttpError(f"{method} {url} failed after retries: {last_error}")

