from __future__ import annotations

import html
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import quote, urlparse

from .http import CachedHttpClient, HttpError
from .roblox import IdentityError
from .util import normalized_name, slugify, utc_now


STORE_SEARCH = "https://store.steampowered.com/api/storesearch/?term={}&l=english&cc=US"
APP_DETAILS = "https://store.steampowered.com/api/appdetails?appids={}&l=english&cc=US"
APP_REVIEWS = (
    "https://store.steampowered.com/appreviews/{}?json=1&language=all"
    "&purchase_type=all&num_per_page=0"
)


def steam_app_id(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "store.steampowered.com", "www.store.steampowered.com"
    }:
        return None
    match = re.match(r"^/app/(\d+)(?:/|$)", parsed.path)
    return match.group(1) if match else None


def _plain_html(value: str | None) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _release_date(value: str | None) -> str | None:
    if not value:
        return None
    for fmt in ("%b %d, %Y", "%d %b, %Y", "%b %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


class SteamClient:
    def __init__(self, http: CachedHttpClient):
        self.http = http

    def discover(self, game_name: str, official_url: str | None = None) -> list[dict[str, Any]]:
        explicit_id = steam_app_id(official_url)
        if official_url and not explicit_id:
            raise IdentityError("Steam official URL must use https://store.steampowered.com/app/<app-id>/")
        if explicit_id:
            details = self._app_details(explicit_id)
            return [{
                "appId": explicit_id,
                "name": details.get("name") or game_name,
                "position": 0,
                "matchScore": 1.0 if normalized_name(details.get("name", "")) == normalized_name(game_name) else 0.0,
                "source": "explicit-official-url",
            }]
        payload = self.http.get_json(STORE_SEARCH.format(quote(game_name)), ttl=86400)
        query = normalized_name(game_name)
        candidates: list[dict[str, Any]] = []
        for position, item in enumerate(payload.get("items") or []):
            if item.get("type") != "app" or not item.get("id"):
                continue
            name = str(item.get("name") or "")
            candidate = normalized_name(name)
            exact = query == candidate
            ratio = SequenceMatcher(None, query, candidate).ratio()
            score = min(1.0, ratio * 0.8 + (0.2 if exact else 0.0) + max(0.0, 0.05 - position * 0.01))
            candidates.append({
                "appId": str(item["id"]), "name": name, "position": position,
                "matchScore": round(score, 4), "source": "steam-store-search",
                "price": item.get("price"), "platforms": item.get("platforms"),
            })
        return sorted(candidates, key=lambda row: (-row["matchScore"], row["position"]))

    def select_identity(self, game_name: str, official_url: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        candidates = self.discover(game_name, official_url)
        if not candidates:
            raise IdentityError(f"No Steam candidates found for {game_name!r}")
        best = candidates[0]
        if best["matchScore"] < 0.9:
            raise IdentityError(
                f"Top Steam candidate confidence {best['matchScore']:.2f} is below 0.90; review candidates in raw/identity.json",
                candidates,
            )
        if len(candidates) > 1 and best["matchScore"] - candidates[1]["matchScore"] < 0.05:
            raise IdentityError("Two Steam candidates are too close to select safely", candidates)
        return best, candidates

    def _app_details(self, app_id: str) -> dict[str, Any]:
        row = self.http.get_json(APP_DETAILS.format(app_id), ttl=3600).get(str(app_id), {})
        if not row.get("success") or not isinstance(row.get("data"), dict):
            raise HttpError(f"Steam returned no app details for {app_id}")
        return row["data"]

    def collect(self, query: str, selected: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        app_id = str(selected["appId"])
        game = self._app_details(app_id)
        reviews = self.http.get_json(APP_REVIEWS.format(app_id), ttl=21600).get("query_summary", {})
        name = str(game["name"])
        canonical_url = f"https://store.steampowered.com/app/{app_id}/{slugify(name).replace('-', '_')}/"
        genres = [str(item.get("description")) for item in game.get("genres", []) if item.get("description")]
        categories = [str(item.get("description")) for item in game.get("categories", []) if item.get("description")]
        price = game.get("price_overview") or {}
        max_players = None
        player_match = re.search(r"up to\s+(\d+)\s+(?:fellow\s+)?friends", game.get("short_description", ""), re.I)
        if player_match:
            max_players = int(player_match.group(1)) + 1
        release = _release_date((game.get("release_date") or {}).get("date"))
        total_reviews = int(reviews.get("total_reviews") or 0)
        total_positive = int(reviews.get("total_positive") or 0)
        approval = round(total_positive / total_reviews * 100, 1) if total_reviews else None
        retrieved = utc_now()
        developer = next(iter(game.get("developers") or []), None)
        website = game.get("website") or None
        screenshots = [item.get("path_full") for item in game.get("screenshots", []) if item.get("path_full")]
        facts = {
            "identity": {
                "query": query, "canonicalName": name, "currentPlatformName": name,
                "slug": slugify(name), "platform": "Steam", "appId": app_id,
                "canonicalUrl": canonical_url, "matchConfidence": selected["matchScore"],
            },
            "developer": {"name": developer, "type": "Studio", "id": None, "url": website, "verified": None},
            "game": {
                "officialDescription": game.get("short_description", ""),
                "detailedDescription": _plain_html(game.get("about_the_game")),
                "genre": genres[0] if genres else None, "genreL1": genres[0] if genres else None,
                "genreL2": genres[1] if len(genres) > 1 else None, "genres": genres,
                "categories": categories, "price": (price.get("final") / 100) if isinstance(price.get("final"), int) else 0 if game.get("is_free") else None,
                "priceCurrency": price.get("currency") or "",
                "priceFormatted": price.get("final_formatted") or ("Free" if game.get("is_free") else None),
                "maxPlayers": max_players, "createdAt": release, "updatedAt": None,
                "isPlayable": not bool((game.get("release_date") or {}).get("coming_soon")),
                "isEarlyAccess": "Early Access" in genres, "platforms": game.get("platforms", {}),
                "controllerSupport": game.get("controller_support"), "achievements": (game.get("achievements") or {}).get("total"),
                "systemRequirements": game.get("pc_requirements", {}),
                "steamTrailers": game.get("movies", []),
            },
            "dynamicStats": {
                "retrievedAt": retrieved, "reviewCount": total_reviews,
                "positiveReviews": total_positive, "approvalPercent": approval,
                "reviewSummary": reviews.get("review_score_desc"),
                "recommendations": (game.get("recommendations") or {}).get("total"),
            },
            "officialLinks": {
                "website": website, "steam": canonical_url, "roblox": None, "robloxGroup": None,
                "discord": None, "reddit": None, "youtube": None, "trailer": None,
                "x": None, "tiktok": None,
            },
            "codes": [], "gameplayFacts": [], "languageSignals": [],
            "media": {
                "icon": game.get("header_image"), "thumbnails": screenshots,
                "heroImages": screenshots[:5] or ([game.get("header_image")] if game.get("header_image") else []),
            },
        }
        evidence = {
            "sources": [
                {"id": "src_steam_store", "url": canonical_url, "title": f"{name} on Steam", "sourceType": "official-platform", "publisher": "Steam", "retrievedAt": retrieved, "httpStatus": 200, "accessible": True},
                {"id": "src_steam_api", "url": APP_DETAILS.format(app_id), "title": "Steam Store app details API", "sourceType": "official-api", "publisher": "Steam", "retrievedAt": retrieved, "httpStatus": 200, "accessible": True},
            ],
            "claims": [
                {"field": field, "sourceIds": ["src_steam_api"], "confidence": 1.0, "classification": "fact"}
                for field in [
                    "identity.appId", "identity.currentPlatformName", "developer.name",
                    "game.officialDescription", "game.createdAt", "game.price",
                    "game.genres", "dynamicStats.reviewCount", "dynamicStats.approvalPercent",
                ]
            ],
        }
        return facts, evidence, {"appDetails": game, "reviewSummary": reviews}
