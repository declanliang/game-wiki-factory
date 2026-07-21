"""Deterministic normalization for simple raw HTML accidentally emitted in MDX prose."""

from __future__ import annotations

import re


def normalize_raw_html_blocks(content: str) -> str:
    """Convert basic heading/list/paragraph HTML to Markdown-safe prose.

    Custom MDX components such as Callout are intentionally preserved.
    """
    for level in range(2, 7):
        content = re.sub(
            rf"<h{level}>\s*(.*?)\s*</h{level}>",
            lambda match, level=level: f"{'#' * level} {match.group(1).strip()}",
            content,
            flags=re.I | re.S,
        )
    content = re.sub(r"</?(?:ul|ol|li|p)(?:\s+[^>]*)?>", "", content, flags=re.I)
    content = re.sub(r"[ \t]+\n", "\n", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()
