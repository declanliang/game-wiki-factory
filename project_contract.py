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


SCHEMA_VERSION = 2
# Default production policy. The template can still support additional locales,
# but new Factory jobs pay for and declare only English and Spanish.
FIXED_LANGUAGES = ["en", "es"]
MINIMUM_CATEGORIES = 1
MAXIMUM_CATEGORIES = 8
MAXIMUM_PROFILE_CANDIDATES = 16

LANGUAGE_NAMES = {
    "en": "English",
    "es": "Español",
    "de": "Deutsch",
    "fr": "Français",
    "ja": "日本語",
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
    "tier-list": {
        "labels": {"en": "Tier List", "es": "Lista de niveles", "de": "Tier-Liste", "fr": "Tier list", "ja": "ティアリスト", "ko": "티어 리스트"},
        "description": "Rankings and comparisons for the game's units, characters, equipment, or other competitive choices.",
        "terms": ["tier list", "ranking", "rankings", "best unit", "best units", "best character", "best characters"],
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
        # This is an allowed planning boundary, not evidence for publishing an
        # economy page.  Reward-loop verbs catch games with named currencies
        # (for example Stars/Zenith) that never use the generic word "currency".
        "terms": [
            "money", "currency", "currencies", "coin", "coins", "cash", "loot",
            "reward", "rewards", "shop", "shops", "earn", "spend", "buy", "purchase",
        ],
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
    "modes": {
        "labels": {"en": "Modes", "es": "Modos", "de": "Modi", "fr": "Modes", "ja": "モード", "ko": "모드"},
        "description": "Game modes, raids, events, challenges, and their objectives.",
        "terms": ["mode", "modes", "raid", "raids", "dungeon", "dungeons", "challenge", "challenges"],
    },
    "items": {
        "labels": {"en": "Items", "es": "Objetos", "de": "Gegenstände", "fr": "Objets", "ja": "アイテム", "ko": "아이템"},
        "description": "Important items, equipment, materials, containers, and how players use them.",
        "terms": ["item", "items", "material", "materials", "container", "containers", "safe", "safes", "equipment"],
    },
    "quests": {
        "labels": {"en": "Quests", "es": "Misiones", "de": "Quests", "fr": "Quêtes", "ja": "クエスト", "ko": "퀘스트"},
        "description": "Quest objectives, NPC tasks, missions, badges, and completion routes.",
        "terms": ["quest", "quests", "mission", "missions", "objective", "objectives", "badge", "badges", "npc"],
    },
    "codes": {
        "labels": {"en": "Codes", "es": "Códigos", "de": "Codes", "fr": "Codes", "ja": "コード", "ko": "코드"},
        "description": "Active codes, rewards, redemption, and expiry status.",
        "terms": ["redeem code", "promo code"],
    },
}

# Category copy is product-owned, stable UI text. Keep it deterministic here so
# every generated site-plan carries localized labels *and* descriptions from the
# same Basic Info-owned source instead of shipping English SEO copy on locale URLs.
CATEGORY_DESCRIPTION_TRANSLATIONS: dict[str, dict[str, str]] = {
    "guide": {"es": "Ayuda para principiantes, controles e información práctica para aprender a jugar.", "de": "Einsteigerhilfe, Steuerung und praktische Anleitungen zum Spielen.", "fr": "Aide aux débutants, commandes et conseils pratiques pour apprendre à jouer.", "ja": "初心者向けの遊び方、操作方法、実践的な攻略情報です。", "ko": "초보자 도움말, 조작법과 실전 플레이 방법을 안내합니다."},
    "progression": {"es": "Cómo funcionan las partidas, los niveles, los desbloqueos y la progresión a largo plazo.", "de": "So funktionieren Runs, Stufen, Freischaltungen und langfristiger Fortschritt.", "fr": "Fonctionnement des parties, niveaux, déblocages et de la progression à long terme.", "ja": "ラン、レベル、アンロック、長期的な進行の仕組みを解説します。", "ko": "런, 레벨, 잠금 해제와 장기 성장 방식을 설명합니다."},
    "mechanics": {"es": "Sistemas principales, reglas, estadísticas e interacciones de juego.", "de": "Kernsysteme, Regeln, Werte und Interaktionen im Spiel.", "fr": "Systèmes principaux, règles, statistiques et interactions de jeu.", "ja": "主要システム、ルール、ステータス、ゲーム内の相互作用を解説します。", "ko": "핵심 시스템, 규칙, 능력치와 게임 상호작용을 설명합니다."},
    "updates": {"es": "Nuevas versiones, cambios, eventos y estado actual del juego.", "de": "Neue Versionen, Änderungen, Events und der aktuelle Spielstatus.", "fr": "Nouvelles versions, changements, événements et état actuel du jeu.", "ja": "新バージョン、変更点、イベント、現在のゲーム状況をまとめます。", "ko": "새 버전, 변경 사항, 이벤트와 현재 게임 상태를 정리합니다."},
    "tier-list": {"es": "Clasificaciones y comparaciones de unidades, personajes, equipo u otras opciones competitivas.", "de": "Ranglisten und Vergleiche für Einheiten, Charaktere, Ausrüstung und andere wichtige Optionen.", "fr": "Classements et comparaisons des unités, personnages, équipements et autres choix importants.", "ja": "ユニット、キャラクター、装備などの選択肢を比較・評価します。", "ko": "유닛, 캐릭터, 장비 등 주요 선택지를 비교하고 평가합니다."},
    "enemies": {"es": "Tipos de enemigos, comportamiento, amenazas y formas de contrarrestarlos.", "de": "Gegnertypen, Verhalten, Gefahren und wirksame Gegenmaßnahmen.", "fr": "Types d'ennemis, comportements, menaces et moyens de les contrer.", "ja": "敵の種類、行動、脅威、対処方法を解説します。", "ko": "적 유형, 행동, 위협 요소와 대응 방법을 설명합니다."},
    "floors": {"es": "Pisos, zonas, mapas, rutas y progresión en profundidad.", "de": "Ebenen, Gebiete, Karten, Routen und Fortschritt in die Tiefe.", "fr": "Étages, zones, cartes, itinéraires et progression en profondeur.", "ja": "フロア、エリア、マップ、ルート、深度進行を解説します。", "ko": "층, 지역, 맵, 이동 경로와 심층 진행을 설명합니다."},
    "upgrades": {"es": "Mejoras, ventajas, configuraciones y crecimiento de poder.", "de": "Upgrades, Vorteile, Builds und die Entwicklung der Kampfstärke.", "fr": "Améliorations, avantages, builds et progression de puissance.", "ja": "強化、パーク、ビルド、戦力の伸ばし方を解説します。", "ko": "업그레이드, 특전, 빌드와 전투력 성장 방법을 설명합니다."},
    "economy": {"es": "Monedas, botín, recompensas, tiendas y prioridades de gasto.", "de": "Währungen, Beute, Belohnungen, Shops und sinnvolle Ausgaben.", "fr": "Monnaies, butin, récompenses, boutiques et priorités de dépense.", "ja": "通貨、戦利品、報酬、ショップ、使い道の優先順位を解説します。", "ko": "재화, 전리품, 보상, 상점과 지출 우선순위를 설명합니다."},
    "bosses": {"es": "Encuentros con jefes, ataques, fases y estrategias.", "de": "Bosskämpfe, Angriffe, Phasen und passende Strategien.", "fr": "Combats de boss, attaques, phases et stratégies.", "ja": "ボス戦、攻撃、フェーズ、攻略方法を解説します。", "ko": "보스 전투, 공격, 페이즈와 공략법을 설명합니다."},
    "weapons": {"es": "Armas, daño, configuraciones y elección de equipamiento.", "de": "Waffen, Schaden, Ausrüstungen und passende Loadouts.", "fr": "Armes, dégâts, équipements et choix de loadout.", "ja": "武器、ダメージ、ロードアウト、装備選びを解説します。", "ko": "무기, 피해량, 로드아웃과 장비 선택을 설명합니다."},
    "characters": {"es": "Personajes jugables, unidades, roles y habilidades.", "de": "Spielbare Charaktere, Einheiten, Rollen und Fähigkeiten.", "fr": "Personnages jouables, unités, rôles et compétences.", "ja": "プレイ可能なキャラクター、ユニット、役割、能力を解説します。", "ko": "플레이 가능한 캐릭터, 유닛, 역할과 능력을 설명합니다."},
    "modes": {"es": "Modos de juego, incursiones, eventos, desafíos y sus objetivos.", "de": "Spielmodi, Raids, Events, Herausforderungen und ihre Ziele.", "fr": "Modes de jeu, raids, événements, défis et leurs objectifs.", "ja": "ゲームモード、レイド、イベント、チャレンジと目標を解説します。", "ko": "게임 모드, 레이드, 이벤트, 도전과 목표를 설명합니다."},
    "items": {"es": "Objetos importantes, equipo, materiales, contenedores y sus usos.", "de": "Wichtige Gegenstände, Ausrüstung, Materialien, Behälter und ihre Verwendung.", "fr": "Objets importants, équipements, matériaux, conteneurs et leurs usages.", "ja": "重要なアイテム、装備、素材、コンテナと使い道を解説します。", "ko": "중요 아이템, 장비, 재료, 상자와 사용처를 설명합니다."},
    "quests": {"es": "Objetivos, tareas de PNJ, misiones, insignias y rutas para completarlas.", "de": "Questziele, NPC-Aufgaben, Missionen, Abzeichen und Lösungswege.", "fr": "Objectifs, tâches de PNJ, missions, badges et parcours de résolution.", "ja": "クエスト目標、NPCの依頼、ミッション、バッジ、攻略ルートを解説します。", "ko": "퀘스트 목표, NPC 임무, 미션, 배지와 완료 경로를 설명합니다."},
    "codes": {"es": "Códigos activos, recompensas, canje y estado de vencimiento.", "de": "Aktive Codes, Belohnungen, Einlösung und Ablaufstatus.", "fr": "Codes actifs, récompenses, utilisation et état d'expiration.", "ja": "有効なコード、報酬、引き換え方法、期限状況をまとめます。", "ko": "사용 가능한 코드, 보상, 입력 방법과 만료 상태를 정리합니다."},
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
    "weapon": "weapons", "units": "characters", "unit": "characters", "heroes": "characters",
    "character": "characters", "classes": "characters",
    "tier list": "tier-list", "tier-lists": "tier-list", "tiers": "tier-list",
    "mode": "modes", "raid": "modes", "raids": "modes",
    "item": "items", "materials": "items", "containers": "items",
    "quest": "quests", "missions": "quests",
    "update": "updates", "news": "updates", "code": "codes",
}

CATEGORY_PRIORITY = {
    "codes": 100,
    "tier-list": 95,
    "characters": 90,
    "modes": 85,
    "items": 80,
    "quests": 75,
    "bosses": 70,
    "upgrades": 65,
    "economy": 60,
    "weapons": 55,
    "enemies": 50,
    "floors": 45,
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
    all_descriptions = {"en": definition["description"], **CATEGORY_DESCRIPTION_TRANSLATIONS[category_id]}
    return {
        "id": category_id,
        "labels": {locale: definition["labels"][locale] for locale in FIXED_LANGUAGES},
        "description": definition["description"],
        "descriptions": {locale: all_descriptions[locale] for locale in FIXED_LANGUAGES},
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
    platforms = site_content.get("site", {}).get("gamePlatform") or []
    platform = str(platforms[0] if platforms else facts.get("identity", {}).get("platform") or "Game")
    if platform.casefold() == "game":
        official_url = str(identity.get("OFFICIAL_GAME_URL") or "").casefold()
        if "roblox.com/" in official_url:
            platform = "Roblox"
        elif "store.steampowered.com/" in official_url:
            platform = "Steam"
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

    # Roblox experiences commonly expose a redeem-code surface outside the
    # official experience description. Keep Codes inside the Basic Info-owned
    # candidate boundary, then require Guide Search evidence before it can be
    # published. This is an allowance, not a synthetic Codes article.
    if platform.casefold() == "roblox" and not any(item["id"] == "codes" for item in dynamic):
        dynamic.append(_candidate("codes", ["roblox-platform-capability"], "basic-info-platform-policy"))

    rankable_terms = ("unit", "units", "character", "characters", "hero", "heroes", "class", "classes", "weapon", "weapons", "trait", "traits", "mutation", "mutations")
    if not any(item["id"] == "tier-list" for item in dynamic) and any(
        re.search(rf"\b{re.escape(term)}\b", corpus) for term in rankable_terms
    ):
        dynamic.append(_candidate("tier-list", ["rankable-entity-category-inference"], "basic-info-inference"))

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
    dynamic.sort(
        key=lambda item: (
            -CATEGORY_PRIORITY.get(item["id"], 0),
            -len(item.get("evidence") or []),
            item["id"],
        )
    )
    # The profile is an allowed semantic vocabulary, not the final navigation.
    # It may be wider than eight so evidence discovered later is not rejected
    # merely because another possible category occupied an early slot. The
    # site plan remains capped at MAXIMUM_CATEGORIES after Guide Search ranks
    # real topics.
    candidates = []
    candidate_ids: set[str] = set()
    for item in [evergreen[0], *dynamic, *evergreen[1:]]:
        if item["id"] in candidate_ids:
            continue
        candidates.append(item)
        candidate_ids.add(item["id"])
    candidates = candidates[:MAXIMUM_PROFILE_CANDIDATES]

    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": _now(),
        "source": "auto-basic-info",
        "game": {
            "name": identity["GAME_NAME"],
            "slug": re.sub(r"[^a-z0-9]+", "-", identity["GAME_NAME"].casefold()).strip("-"),
            "platform": platform,
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
        raw_topics = raw.get("topics") or []
        topics_by_keyword = {
            str(item.get("keyword") or "").strip(): item
            for item in raw_topics
            if isinstance(item, dict) and str(item.get("keyword") or "").strip()
        }
        topics = []
        for keyword in keywords:
            source = topics_by_keyword.get(keyword) or {}
            intent = str(source.get("intent") or "").strip()
            discovery_sources = list(source.get("discoverySources") or [])
            platform = str(profile.get("game", {}).get("platform") or "Game").strip()
            research_query = (
                keyword
                if platform.casefold() in keyword.casefold().split()
                else f"{platform} {keyword}"
            )
            if any(item in {"labs", "autocomplete", "trends"} for item in discovery_sources):
                demand_class = "query-backed"
            elif source.get("entityName"):
                demand_class = "entity-backed"
            else:
                demand_class = "evidence-backed"
            topics.append({
                "keyword": keyword,
                "primaryKeyword": keyword,
                "researchQuery": research_query,
                "pageType": str(source.get("pageType") or "guide"),
                "entityName": source.get("entityName"),
                "entityType": source.get("entityType"),
                "intent": intent,
                "userQuestion": intent or f"What should a player know about {keyword}?",
                "mustAnswer": [
                    intent or f"Give a direct, game-specific answer for {keyword}."
                ],
                "distinctValue": (
                    intent
                    or f"Resolve the specific player decision expressed by {keyword}."
                ),
                "allowedSharedContext": [
                    "brief game identity",
                    "relevant prerequisites",
                    "closely related mechanics",
                ],
                "overlapPolicy": (
                    "Limited shared background is allowed. The page must still deliver "
                    "its own primary answer and must not become a wording-only copy of "
                    "another page."
                ),
                "demandClass": demand_class,
                "confidence": source.get("confidence"),
                "discoverySources": discovery_sources,
                "evidenceUrls": list(source.get("evidenceUrls") or []),
            })
        if category_id not in allowed:
            rejected.append({"category": raw_name, "reason": "not-allowed-by-basic-info-profile"})
            continue
        if not keywords:
            rejected.append({"category": raw_name, "reason": "no-usable-keywords"})
            continue
        if category_id in seen:
            existing = next(item for item in selected if item["id"] == category_id)
            existing["keywords"] = list(dict.fromkeys([*existing["keywords"], *keywords]))
            existing_topic_keywords = {item["keyword"] for item in existing["topics"]}
            existing["topics"].extend(item for item in topics if item["keyword"] not in existing_topic_keywords)
            continue
        candidate = allowed[category_id]
        selected.append({
            "id": category_id,
            "order": len(selected) + 1,
            "labels": candidate["labels"],
            "description": candidate["description"],
            "descriptions": candidate["descriptions"],
            "keywords": keywords,
            "topics": topics,
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
    platform = site_plan["game"].get("platform") or "Game"
    topic_specs = {
        topic["keyword"]: {
            key: value
            for key, value in topic.items()
            if key != "keyword" and value not in (None, "", [], {})
        }
        for item in site_plan["categories"]
        for topic in item.get("topics") or []
    }
    return {
        "game_name": game_name,
        "filter_keyword": f"{platform} {game_name}",
        "languages": [locale for locale in site_plan["languages"] if locale != "en"],
        "trusted_context": {
            "game": site_plan["game"],
            "category_descriptions": {
                item["id"]: item["description"] for item in site_plan["categories"]
            },
            "policy": "Use as trusted same-game context; search titles are discovery evidence, not verified numeric facts.",
        },
        "topic_specs": topic_specs,
        "categories": [
            {
                "category": item["id"],
                "keywords": item["keywords"],
                "topics": item.get("topics") or [],
            }
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


def render_project_readme(
    game_name: str,
    platform: str = "Roblox",
    official_url: str = "",
) -> str:
    platform_key = platform.casefold()
    command = f'python gamewiki.py "{game_name}" --platform {platform_key}'
    if platform_key == "steam" and official_url:
        command += f' --official-url "{official_url}"'
    platform_notes = ""
    if platform_key == "steam":
        platform_notes = """

## Steam 数据边界

- App ID 是稳定身份；续跑时保留 `--platform steam` 和官方 Store URL。
- 价格、评价数量和 Early Access 状态是采集时快照，可能随时间变化。
- `full controller support` 不等于 Steam Deck Verified/Playable；Windows 要求也不能证明 SteamOS 性能。
- 普通续跑会复用 checkpoint。不要随意使用 refresh/recluster/overwrite，以免重复产生 API 费用。
"""
    return f"""# {game_name} Wiki

这是由 `game-wiki-factory` 生成的独立 Next.js 游戏攻略站。本目录就是 GitHub 仓库和 Cloudflare Pages 项目根目录，不存在额外的 `site/` 子目录。

## 目录

- `intake/`：网站最终输入的唯一事实源，包含身份、已生成语言首页配置、site-plan、素材和文章；应提交 Git。
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
{command}
```

同一命令自动复用已验证 checkpoint。除非日志证明缓存无效，不要使用 refresh/overwrite 参数。

## 部署

Factory 会把本目录推送为一个独立 Private GitHub repo，并创建连接该 repo `main` 分支的 Cloudflare Pages 项目；Root Directory 留空，Build command 为 `npm run build`，Build output 为 `out`。发布器会设置 `NEXT_PUBLIC_SITE_URL=https://正式域名` 并运行线上验收；若正式域名仍在 DNS/验证 pending，按 Cloudflare 控制台提示完成后再运行 `npm run verify:deploy`。
{platform_notes}
"""
