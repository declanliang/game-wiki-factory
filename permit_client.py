"""Small cross-process permit client used by orchestrated build stages."""

from __future__ import annotations

import json
import os
import urllib.request
from contextlib import contextmanager


@contextmanager
def shared_permit(*resources: str):
    url = os.getenv("GAMEWIKI_PERMIT_URL", "").rstrip("/")
    token = os.getenv("GAMEWIKI_PERMIT_TOKEN", "")
    if not url:
        yield
        return
    request = urllib.request.Request(
        f"{url}/acquire",
        data=json.dumps({"resources": list(resources)}).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=3600) as response:
        lease = json.loads(response.read().decode("utf-8"))["lease"]
    try:
        yield
    finally:
        release = urllib.request.Request(
            f"{url}/release",
            data=json.dumps({"lease": lease}).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(release, timeout=30):
            pass
