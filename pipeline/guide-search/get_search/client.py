from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class DataForSEOError(RuntimeError):
    pass


@dataclass
class ApiCall:
    endpoint: str
    response: dict[str, Any]

    @property
    def cost(self) -> float:
        return float(self.response.get("cost") or 0)


class DataForSEOClient:
    BASE_URL = "https://api.dataforseo.com"

    def __init__(self, login: str, password: str, timeout: int = 120) -> None:
        token = base64.b64encode(f"{login}:{password}".encode("utf-8")).decode("ascii")
        self._authorization = f"Basic {token}"
        self.timeout = timeout

    def post(self, endpoint: str, task: dict[str, Any]) -> ApiCall:
        payload = json.dumps([task], ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.BASE_URL}{endpoint}",
            data=payload,
            headers={
                "Authorization": self._authorization,
                "Content-Type": "application/json",
                "User-Agent": "get-search/0.1",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise DataForSEOError(f"HTTP {exc.code} from {endpoint}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise DataForSEOError(f"Network error from {endpoint}: {exc.reason}") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise DataForSEOError(f"Invalid JSON from {endpoint}") from exc

        status = int(parsed.get("status_code") or 0)
        if status != 20000:
            raise DataForSEOError(
                f"DataForSEO {status} from {endpoint}: {parsed.get('status_message', 'unknown error')}"
            )
        tasks = parsed.get("tasks") or []
        if tasks and int(tasks[0].get("status_code") or 0) != 20000:
            task_status = tasks[0].get("status_code")
            message = tasks[0].get("status_message", "unknown task error")
            raise DataForSEOError(f"DataForSEO task {task_status} from {endpoint}: {message}")
        return ApiCall(endpoint=endpoint, response=parsed)


def first_task_results(response: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = response.get("tasks") or []
    if not tasks:
        return []
    results = tasks[0].get("result") or []
    return [item for item in results if isinstance(item, dict)]

