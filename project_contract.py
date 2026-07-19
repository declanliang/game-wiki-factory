"""Deterministic contracts shared by the game-wiki pipeline stages.

Basic Info owns the game profile and its allowed category candidates.  Guide
Search may rank and supply keywords, but it cannot invent a downstream category.
The resulting site-plan is the only file consumed by SEO Scout and the template.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
FIXED_LANGUAGES = ["en", "es", "de", "fr", "ja", "ko"]
MINIMUM_CATEGORIES = 1
MAXIMUM_CATEGORIES = 8

LANGUAGE_NAMES = {
    "en": "English",
    "es": "Español",
    "de": "Deutsch",
    "fr": "Français",
    "ja": "日本語",
    "ko": "한국어",
}

# Four evergreen information architectures are always useful for a guide site.
# Dynamic candidates are admitted only when Basic Info contains a matching term.
CATEGORY_DEFINITIONS: dict[str, dict[str, Any]] = {
    "guide": {
        "labels": {"en": "Guides", "es": "Guías", "de": "Anleitungen", "fr": "Guides", "ja": "ガイド", "ko": "가이드"},
        "description": "Beginner help, controls, and practical how-to information.",
        "always": True,
    },
    "progression": {
        "labels": {"en": "Progression", "es": "Progresión", "de": "Fortschritt", "fr": "Progression", "ja": "進行", "ko": "진행"},
        "description": "How runs, levels, unlocks, and long-term progress work.",
        "always": True,
    },
    "mechanics": {
        "labels": {"en": "Mechanics", "es": "Mecánicas", "de": "Mechaniken", "fr": "Mécaniques", "ja": "ゲームシステム", "ko": "게임 시스템"},
        "description": "Core systems, rules, stats, and gameplay interactions.",
        "always": True,
    },
    "updates": {
        "labels": {"en": "Updates", "es": "Actualizaciones", "de": "Updates", "fr": "Mises à jour", "ja": "アップデート", "ko": "업데이트"},
        "description": "New versions, changes, events, and current game status.",
        "always": True,
    },
    "enemies": {
        "labels": {"en": "Enemies", "es": "Enemigos", "de": "Gegner", "fr": "Ennemis", "ja": "敵", "ko": "적"},
        "description": "Enemy types, behavior, threats, and counterplay.",
        "terms": ["enemy", "enemies", "horde", "monster", "hostile", "zombie"],
    },
    "floors": {
        "labels": {"en": "Floors", "es": "Pisos", "de": "Ebenen", "fr": "Étages", "ja": "フロア", "ko": "층"},
        "description": "Floors, areas, maps, routes, and depth progression.",
        "terms": ["floor", "floors", "shaft", "depth", "deeper", "map", "maps", "area", "areas", "world", "worlds"],
    },
    "upgrades": {
        "labels": {"en": "Upgrades", "es": "Mejoras", "de": "Upgrades", "fr": "Améliorations", "ja": "強化", "ko": "업그레이드"},
        "description": "Upgrades, perks, builds, and power growth.",
        "terms": ["upgrade", "upgrades", "perk", "perks", "build", "builds", "power", "skill", "skills", "trait", "traits"],
    },
    "economy": {
        "labels": {"en": "Economy", "es": "Economía", "de": "Wirtschaft", "fr": "Économie", "ja": "経済", "ko": "경제"},
        "description": "Currencies, loot, rewards, shops, and spending priorities.",
        "terms": ["money", "currency", "coin", "cash", "loot", "reward", "shop"],
    },
    "bosses": {
        "labels": {"en": "Bosses", "es": "Jefes", "de": "Bosse", "fr": "Boss", "ja": "ボス", "ko": "보스"},
        "description": "Boss encounters, attacks, phases, and strategies.",
        "terms": ["boss", "bosses", "raid", "raids"],
    },
    "weapons": {
        "labels": {"en": "Weapons", "es": "Armas", "de": "Waffen", "fr": "Armes", "ja": "武器", "ko": "무기"},
        "description": "Weapons, damage, loadouts, and equipment choices.",
        "terms": ["weapon", "weapons", "gun", "guns", "shoot", "sword", "swords", "equipment", "loadout", "loadouts"],
    },
    "characters": {
        "labels": {"en": "Characters", "es": "Personajes", "de": "Charaktere", "fr": "Personnages", "ja": "キャラクター", "ko": "캐릭터"},
        "description": "Playable characters, units, roles, and abilities.",
        "terms": ["character", "characters", "unit", "units", "hero", "heroes", "class", "classes", "role", "roles"],
    },
    "codes": {
        "labels": {"en": "Codes", "es": "Códigos", "de": "Codes", "fr": "Codes", "ja": "コード", "ko": "코드"},
        "description": "Active codes, rewards, redemption, and expiry status.",
        "terms": ["redeem code", "promo code"],
    },
}

CATEGORY_ALIASES = {
    "guides": "guide", "beginner": "guide", "beginners": "guide",
    "strategy": "guide", "strategies": "guide", "tips": "guide", "tactics": "guide",
    "gameplay": "mechanics", "system": "mechanics", "systems": "mechanics",
    "levels": "progression", "leveling": "progression", "levelling": "progression",
    "maps": "floors", "areas": "floors", "worlds": "floors",
    "enemy": "enemies", "monsters": "enemies", "mobs": "enemies",
    "boss": "bosses", "upgrade": "upgrades", "perks": "upgrades",
    "currency": "economy", "currencies": "economy", "loot": "economy",
    "weapon": "weapons", "units": "characters", "heroes": "characters",
    "update": "updates", "news": "updates", "code": "codes",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in _text_values(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _text_values(item)]
    return []


def _candidate(category_id: str, evidence: list[str], source: str) -> dict[str, Any]:
    definition = CATEGORY_DEFINITIONS[category_id]
    return {
        "id": category_id,
        "labels": definition["labels"],
        "description": definition["description"],
        "source": source,
        "evidence": evidence[:8],
    }


def build_game_profile(basic_output: Path) -> dict[str, Any]:
    """Create the Basic-Info-owned semantic boundary for downstream work."""
    output = basic_output.resolve()
    intake = output / "template-intake" if (output / "template-intake").is_dir() else output
    identity = read_json(intake / "site-identity.json")
    site_content = read_json(intake / "site-content.json")
    facts_path = output / "facts.json"
    facts = read_json(facts_path) if facts_path.is_file() else {}
    corpus = "\n".join(_text_values({"facts": facts, "siteContent": site_content})).casefold()

    dynamic: list[dict[str, Any]] = []
    for category_id, definition in CATEGORY_DEFINITIONS.items():
        if definition.get("always"):
            continue
        terms = [
            term
            for term in definition.get("terms", [])
            if re.search(rf"\b{re.escape(term.casefold())}\b", corpus)
        ]
        if category_id == "codes" and facts.get("codes"):
            terms.append("facts.codes")
        if terms:
            dynamic.append(_candidate(category_id, sorted(set(terms)), "basic-info-evidence"))

    if not any(item["id"] == "bosses" for item in dynamic) and any(
        term in corpus for term in ("shooter", "combat", "fight", "enemy", "horde", "weapon")
    ):
        inferred_bosses = _candidate("bosses", ["combat-game-category-inference"], "basic-info-inference")
        lower_priority = next(
            (index for index, item in enumerate(dynamic) if item["id"] in {"weapons", "characters", "codes"}),
            len(dynamic),
        )
        dynamic.insert(lower_priority, inferred_bosses)

    evergreen = [
        _candidate(category_id, ["guide-site-policy"], "basic-info-policy")
        for category_id in ("guide", "updates", "progression", "mechanics")
    ]
    # Prefer game-specific information architecture. Updates gets one reserved
    # slot because every live game changes; progression/mechanics are fallbacks
    # used only when Basic Info is sparse.
    candidates = [evergreen[0], *dynamic[:6], evergreen[1]][:MAXIMUM_CATEGORIES]
    candidate_ids = {item["id"] for item in candidates}
    for fallback in evergreen:
        if len(candidates) >= MINIMUM_CATEGORIES:
            break
        if fallback["id"] not in candidate_ids:
            candidates.append(fallback)
            candidate_ids.add(fallback["id"])

    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": _now(),
        "source": "auto-basic-info",
        "game": {
            "name": identity["GAME_NAME"],
            "slug": re.sub(r"[^a-z0-9]+", "-", identity["GAME_NAME"].casefold()).strip("-"),
            "platform": "Roblox",
            "officialUrl": identity.get("OFFICIAL_GAME_URL"),
            "summary": site_content.get("site", {}).get("description", ""),
        },
        "languages": list(FIXED_LANGUAGES),
        "categoryPolicy": {"minimum": MINIMUM_CATEGORIES, "maximum": MAXIMUM_CATEGORIES},
        "categoryCandidates": candidates,
    }


def normalize_category(value: str) -> str:
    category = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return CATEGORY_ALIASES.get(category, category)


def build_site_plan(profile: dict[str, Any], keyword_output: dict[str, Any]) -> dict[str, Any]:
    """Merge ranked keyword evidence inside the Basic Info category boundary."""
    allowed = {item["id"]: item for item in profile["categoryCandidates"]}
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    seen: set[str] = set()

    for raw in keyword_output.get("categories") or []:
        raw_name = str(raw.get("category") or "").strip()
        category_id = normalize_category(raw_name)
        keywords = list(dict.fromkeys(
            str(item).strip() for item in (raw.get("keywords") or []) if str(item).strip()
        ))
        if category_id not in allowed:
            rejected.append({"category": raw_name, "reason": "not-allowed-by-basic-info-profile"})
            continue
        if not keywords:
            rejected.append({"category": raw_name, "reason": "no-usable-keywords"})
            continue
        if category_id in seen:
            existing = next(item for item in selected if item["id"] == category_id)
            existing["keywords"] = list(dict.fromkeys([*existing["keywords"], *keywords]))
            continue
        candidate = allowed[category_id]
        selected.append({
            "id": category_id,
            "order": len(selected) + 1,
            "labels": candidate["labels"],
            "description": candidate["description"],
            "keywords": keywords,
            "status": "planned",
            "articleCount": 0,
            "sources": [candidate["source"], "guide-search"],
        })
        seen.add(category_id)

    if len(selected) < MINIMUM_CATEGORIES:
        raise ValueError(
            "Guide Search did not deliver any evidence-backed category inside the "
            "Basic Info profile boundary."
        )
    selected = selected[:MAXIMUM_CATEGORIES]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": _now(),
        "game": profile["game"],
        "languages": list(profile["languages"]),
        "categoryPolicy": copy.deepcopy(profile["categoryPolicy"]),
        "categories": selected,
        "rejectedCategoryProposals": rejected,
    }


def build_seo_keywords(site_plan: dict[str, Any]) -> dict[str, Any]:
    game_name = site_plan["game"]["name"]
    return {
        "game_name": game_name,
        "filter_keyword": f"Roblox {game_name}",
        "languages": [locale for locale in site_plan["languages"] if locale != "en"],
        "trusted_context": {
            "game": site_plan["game"],
            "category_descriptions": {
                item["id"]: item["description"] for item in site_plan["categories"]
            },
            "policy": "Use as trusted same-game context; search titles are discovery evidence, not verified numeric facts.",
        },
        "categories": [
            {"category": item["id"], "keywords": item["keywords"]}
            for item in site_plan["categories"]
            if item["status"] in {"planned", "published"}
        ],
    }


def reconcile_site_plan(site_plan: dict[str, Any], articles_dir: Path) -> dict[str, Any]:
    """Record actual English delivery without changing category ownership."""
    result = copy.deepcopy(site_plan)
    en_dir = articles_dir / "en"
    counts: dict[str, int] = {}
    if en_dir.is_dir():
        for category_dir in en_dir.iterdir():
            if category_dir.is_dir():
                counts[category_dir.name] = len(list(category_dir.rglob("*.mdx")))
    for category in result["categories"]:
        count = counts.get(category["id"], 0)
        category["articleCount"] = count
        category["status"] = "published" if count else "unfulfilled"
    result["reconciledAt"] = _now()
    result["qualityGate"] = {
        "publishedCategoryCount": sum(item["status"] == "published" for item in result["categories"]),
        "minimumCategoryCount": result["categoryPolicy"]["minimum"],
    }
    if result["qualityGate"]["publishedCategoryCount"] < result["qualityGate"]["minimumCategoryCount"]:
        raise ValueError(
            "Article QA left only "
            f"{result['qualityGate']['publishedCategoryCount']} published categories; "
            f"minimum is {result['qualityGate']['minimumCategoryCount']}."
        )
    return result


def render_project_readme(game_name: str) -> str:
    return f"""# {game_name} Wiki

这是由 `game-wiki-factory` 生成的独立 Next.js 游戏攻略站。本目录就是 GitHub/Vercel 项目根目录，不存在额外的 `site/` 子目录。

## 目录

- `intake/`：网站最终输入的唯一事实源，包含身份、六语言首页配置、site-plan、素材和文章；应提交 Git。
- `content/`、`src/config/site-plan.json`、`src/locales/`、`public/`：从 intake 机械生成的网站投影。
- `.gamewiki/manifest.json`：可续跑 stage 状态和路径。
- `.gamewiki/planning/`：game profile、Guide Search、site plan 和关键词决策。
- `.gamewiki/content-pipeline/`：SEO Scout 搜索、QA、文章、翻译和 cache。
- `.gamewiki/logs/`：每次执行的完整日志；`.gamewiki/` 默认不提交 Git。

## 本地网站

```powershell
npm ci
npm run dev
```

重新从 intake 物化并完成生产验收：

```powershell
npm run launch:site
```

## 续跑内容工厂

从同级 `game-wiki-factory` 执行：

```powershell
cd ..\\game-wiki-factory
python gamewiki.py "{game_name}"
```

同一命令自动复用已验证 checkpoint。除非日志证明缓存无效，不要使用 refresh/overwrite 参数。

## 部署

把本目录推送为一个独立 GitHub repo，在 Vercel 直接导入；Root Directory 留空。部署前设置 `NEXT_PUBLIC_SITE_URL=https://正式域名`（公开变量，无需 Sensitive；裸域名会自动补 HTTPS），并运行 `npm run verify:deploy`。
"""
