from __future__ import annotations

from typing import Any

from .util import compact_number


def render_basic_info(facts: dict[str, Any], evidence: dict[str, Any], homepage: dict[str, Any], validation: dict[str, Any]) -> str:
    identity = facts["identity"]
    links = facts["officialLinks"]
    stats = facts["dynamicStats"]
    home = homepage["home"]
    lines = [
        f"# {identity['canonicalName']} 首页基础信息",
        "",
        f"> 自动采集状态：**{validation['status']}** · Roblox 数据时间：{stats['retrievedAt']}",
        "",
        "## 1. 游戏身份与官方链接",
        "",
        f"- Roblox：[Play {identity['currentRobloxName']}]({identity['canonicalUrl']})",
        f"- Place ID：`{identity['placeId']}`",
        f"- Universe ID：`{identity['universeId']}`",
        f"- Developer：{facts['developer'].get('name') or 'Unknown'}",
    ]
    for label, key in [("Developer page", "robloxGroup"), ("Website", "website"), ("Discord", "discord"), ("YouTube", "youtube"), ("Trailer", "trailer"), ("X", "x"), ("TikTok", "tiktok"), ("Reddit", "reddit")]:
        if links.get(key):
            lines.append(f"- {label}：[{links[key]}]({links[key]})")
    lines += [
        "", "## 2. Roblox 官方数据", "",
        f"- Players online：{compact_number(stats.get('playing'))}",
        f"- Visits：{compact_number(stats.get('visits'))}",
        f"- Favorites：{compact_number(stats.get('favorites'))}",
        f"- Approval：{stats.get('approvalPercent')}%" if stats.get("approvalPercent") is not None else "- Approval：Unknown",
        f"- Max players：{facts['game'].get('maxPlayers') or 'Unknown'}",
        f"- Created：{facts['game'].get('createdAt') or 'Unknown'}",
        f"- Updated：{facts['game'].get('updatedAt') or 'Unknown'}",
        "", "## 3. SEO 与 Hero", "",
        f"- Title：{homepage['metadata']['title']}",
        f"- Description：{homepage['metadata']['description']}",
        f"- Keywords：{homepage['metadata']['keywords']}",
        f"- Eyebrow：{home['hero']['eyebrow']}",
        f"- Hero title：{home['hero']['title']}",
        f"- Hero description：{home['hero']['description']}",
        "- Stats：" + " · ".join(home["hero"]["stats"]),
        "", "## 4. Start cards", "",
    ]
    for card in home["start"]["cards"]:
        lines.append(f"{card['number']}. **{card['title']}** — {card['description']}")
    lines += ["", "## 5. About Game", ""]
    lines.extend(home["aboutGame"]["paragraphs"])
    lines += ["", "| Field | Value |", "|---|---|"]
    lines.extend(f"| {item['label']} | {item['value']} |" for item in home["aboutGame"]["stats"])
    lines += ["", "## 6. Theme", "", f"- Default：`{homepage['theme']['defaultMode']}`", f"- Light：`{homepage['theme']['light']['navTheme']}` / `{homepage['theme']['light']['navThemeLight']}`", f"- Dark：`{homepage['theme']['dark']['navTheme']}` / `{homepage['theme']['dark']['navThemeLight']}`", f"- Reason：{homepage['theme']['reason']}", "", "## 7. Languages", ""]
    lines.extend(f"{lang['rank']}. **{lang['language']}** (`{lang['code']}`) — {lang['localizedSiteName']} ({lang['basis']}, {lang['confidence']:.2f})" for lang in homepage["languages"])
    lines += ["", "## 8. Codes", ""]
    lines.extend(f"- `{code['code']}` — {code['reward']} · {code['status']}" for code in homepage["sidebarCodes"])
    lines += ["", "## 9. Favicon Prompt", "", homepage["faviconPrompt"], "", "## 10. Validation", "", f"- Status：**{validation['status']}**", f"- Required fields：{validation['metrics']['requiredFieldsComplete']:.1%}", f"- Facts with sources：{validation['metrics']['factsWithSources']:.1%}", f"- Official source ratio：{validation['metrics']['officialSourceRatio']:.1%}"]
    for issue in validation["errors"] + validation["warnings"]:
        lines.append(f"- `{issue['code']}` {issue['field']}：{issue['message']}")
    lines += ["", "## 11. Sources", ""]
    for source in evidence.get("sources", []):
        lines.append(f"- [{source.get('title') or source['url']}]({source['url']}) — {source.get('sourceType', 'unknown')}")
    return "\n".join(lines) + "\n"

