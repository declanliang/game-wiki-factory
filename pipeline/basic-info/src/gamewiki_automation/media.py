from __future__ import annotations

import colorsys
import io
import json
from pathlib import Path
from typing import Any

import requests
from PIL import Image

from .util import dump_json, utc_now


def _download_image(url: str, timeout: int = 60) -> tuple[bytes, str]:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "gamewiki-automation/0.1"})
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("image/"):
        raise ValueError(f"not an image: {content_type}")
    if len(response.content) > 20 * 1024 * 1024:
        raise ValueError("image exceeds 20 MB")
    return response.content, content_type


def _dominant_hsl(image: Image.Image, count: int = 4) -> list[str]:
    rgb = image.convert("RGB")
    rgb.thumbnail((128, 128))
    quantized = rgb.quantize(colors=count, method=Image.Quantize.MEDIANCUT).convert("RGB")
    colors = quantized.getcolors(128 * 128) or []
    result: list[str] = []
    for _, (r, g, b) in sorted(colors, reverse=True):
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if l < 0.08 or l > 0.94:
            continue
        value = f"{round(h * 360)} {round(s * 100)}% {round(l * 100)}%"
        if value not in result:
            result.append(value)
    return result[:count]


def build_assets(facts: dict[str, Any], assets_dir: Path) -> tuple[dict[str, Any], list[str]]:
    assets_dir.mkdir(parents=True, exist_ok=True)
    favicon_dir = assets_dir / "favicon"
    hero_dir = assets_dir / "hero"
    favicon_dir.mkdir(exist_ok=True)
    hero_dir.mkdir(exist_ok=True)
    report: dict[str, Any] = {"retrievedAt": utc_now(), "icon": None, "heroImages": [], "errors": []}
    palette: list[str] = []
    icon_url = facts.get("media", {}).get("icon")
    if icon_url:
        try:
            body, content_type = _download_image(icon_url)
            image = Image.open(io.BytesIO(body)).convert("RGBA")
            image.save(favicon_dir / "source-icon.png", format="PNG")
            palette = _dominant_hsl(image)
            sizes = {
                "favicon-16x16.png": 16, "favicon-32x32.png": 32,
                "apple-touch-icon.png": 180, "android-chrome-192x192.png": 192,
                "android-chrome-512x512.png": 512,
            }
            for name, size in sizes.items():
                image.resize((size, size), Image.Resampling.LANCZOS).save(favicon_dir / name, "PNG")
            image.resize((64, 64), Image.Resampling.LANCZOS).save(
                favicon_dir / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)]
            )
            manifest = {
                "name": facts["identity"]["canonicalName"] + " Wiki",
                "short_name": facts["identity"]["canonicalName"],
                "icons": [
                    {"src": "android-chrome-192x192.png", "sizes": "192x192", "type": "image/png"},
                    {"src": "android-chrome-512x512.png", "sizes": "512x512", "type": "image/png"},
                ],
                "theme_color": "#111827", "background_color": "#111827", "display": "standalone",
            }
            (favicon_dir / "site.webmanifest").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            report["icon"] = {"url": icon_url, "width": image.width, "height": image.height, "contentType": content_type, "paletteHsl": palette}
        except Exception as exc:
            report["errors"].append(f"favicon: {exc}")
    for index, url in enumerate(facts.get("media", {}).get("heroImages", [])[:5], 1):
        try:
            body, content_type = _download_image(url)
            image = Image.open(io.BytesIO(body))
            if image.width / max(1, image.height) < 1.3:
                raise ValueError(f"aspect ratio {image.width}:{image.height} is not landscape")
            extension = ".png" if "png" in content_type.lower() else ".webp" if "webp" in content_type.lower() else ".jpg"
            path = hero_dir / f"hero-{index}{extension}"
            path.write_bytes(body)
            report["heroImages"].append({"url": url, "file": str(path.relative_to(assets_dir.parent)), "width": image.width, "height": image.height, "contentType": content_type})
        except Exception as exc:
            report["errors"].append(f"hero {index}: {exc}")
    dump_json(assets_dir / "media.json", report)
    return report, palette

