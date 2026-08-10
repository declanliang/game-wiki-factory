from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from .http import CachedHttpClient, HttpError
from .util import normalized_name, slugify, utc_now


DISCOVER = "https://r.jina.ai/https://www.roblox.com/discover/?Keyword={}"


class IdentityError(RuntimeError):
    def __init__(self, message: str, candidates: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.candidates = candidates or []


def _name_tokens(value: str) -> list[str]:
    value = re.sub(r"\[[^]]*]|\([^)]*\)", " ", value.casefold())
    return re.findall(r"[a-z0-9]+", value)


def clean_roblox_display_name(value: str) -> str:
    """Remove update tags and decorative emoji without losing disambiguators."""
    value = re.sub(r"\s*\[[^]]+]\s*", " ", value)
    value = re.sub(
        "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\uFE0F\u200D]",
        "",
        value,
    )
    return re.sub(r"\s+", " ", value).strip()


def roblox_place_id(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "roblox.com", "www.roblox.com"
    }:
        return None
    match = re.match(r"^/games/(\d+)(?:/|$)", parsed.path)
    return match.group(1) if match else None


def identity_match_confidence(selected: dict[str, Any]) -> float:
    """Return the confidence exposed to validators and downstream consumers.

    An explicit official URL resolves an immutable Roblox Place ID through the
    Roblox API.  Its name similarity remains useful audit data in ``matchScore``,
    but it must not downgrade the confidence of the resolved identity.
    """
    if selected.get("identitySelection") == "explicit-place-id":
        return 1.0
    return float(selected["matchScore"])


class RobloxClient:
    def __init__(self, http: CachedHttpClient):
        self.http = http

    def _game_rows(self, universe_ids: str) -> tuple[list[dict[str, Any]], str]:
        """Read official game details with a resilient API fallback.

        Roblox has intermittently returned a policy 403 from the public
        ``games.roblox.com/v1/games`` endpoint for some network egresses while
        the official Develop API remains available.  The fallback intentionally
        exposes only fields supplied by Roblox; unknown fields stay absent and
        are handled as null downstream.
        """
        try:
            return (
                self.http.get_json(
                    f"https://games.roblox.com/v1/games?universeIds={universe_ids}",
                    ttl=86400,
                ).get("data", []),
                "https://games.roblox.com/v1/games",
            )
        except HttpError as exc:
            if "HTTP 403" not in str(exc):
                raise
            rows: list[dict[str, Any]] = []
            for universe_id in [item.strip() for item in universe_ids.split(",") if item.strip()]:
                detail = self.http.get_json(
                    f"https://develop.roblox.com/v1/universes/{universe_id}",
                    ttl=86400,
                )
                creator_type = detail.get("creatorType")
                creator_id = detail.get("creatorTargetId")
                rows.append(
                    {
                        "id": detail.get("id"),
                        "name": detail.get("name"),
                        "description": detail.get("description", ""),
                        "rootPlaceId": detail.get("rootPlaceId"),
                        "created": detail.get("created"),
                        "updated": detail.get("updated"),
                        "isPlayable": detail.get("isActive"),
                        "creator": (
                            {
                                "type": creator_type,
                                "id": creator_id,
                                "name": detail.get("creatorName"),
                            }
                            if creator_type or creator_id or detail.get("creatorName")
                            else None
                        ),
                    }
                )
            return rows, "https://develop.roblox.com/v1/universes"

    def discover(
        self, game_name: str, limit: int = 12, official_url: str | None = None
    ) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        seen: set[str] = set()
        explicit_id = roblox_place_id(official_url)
        if official_url and not explicit_id:
            raise IdentityError("Roblox official URL must use https://www.roblox.com/games/<place-id>/")
        if explicit_id:
            found.append({
                "placeId": explicit_id, "universeId": None,
                "slugFromSearch": urlparse(official_url).path.split("/", 3)[-1],
                "position": 0, "source": "explicit-official-url",
            })
        else:
            response = self.http.get(DISCOVER.format(quote(game_name)), ttl=3600)
            if response.status_code >= 400:
                raise IdentityError(f"Roblox Discover reader returned HTTP {response.status_code}")
            pattern = re.compile(r"https?://(?:www\.)?roblox\.com/games/(\d+)(?:/([^\s)\]]+))?", re.I)
            for match in pattern.finditer(response.text):
                place_id, tail = match.groups()
                if place_id in seen:
                    continue
                seen.add(place_id)
                tail = tail or ""
                parsed = urlparse("https://www.roblox.com/" + tail)
                universe = parse_qs(parsed.query).get("universeId", [None])[0]
                found.append({
                    "placeId": place_id,
                    "universeId": universe,
                    "slugFromSearch": parsed.path.strip("/"),
                    "position": len(found),
                })
                if len(found) >= limit:
                    break
            if not found:
                raise IdentityError(f"No Roblox candidates found for {game_name!r}")
        missing = [item for item in found if not item["universeId"]]
        for item in missing:
            data = self.http.get_json(
                f"https://apis.roblox.com/universes/v1/places/{item['placeId']}/universe",
                ttl=30 * 86400,
            )
            item["universeId"] = str(data["universeId"])
        universe_ids = ",".join(item["universeId"] for item in found)
        games, _ = self._game_rows(universe_ids)
        by_id = {str(game["id"]): game for game in games}
        query_norm = normalized_name(game_name)
        query_tokens = {token for token in _name_tokens(game_name) if token not in {"a", "an", "the"}}
        for item in found:
            game = by_id.get(item["universeId"], {})
            item["name"] = game.get("name") or item["slugFromSearch"].replace("-", " ")
            item["creator"] = game.get("creator")
            item["description"] = game.get("description", "")
            item["visits"] = game.get("visits")
            candidate_norm = normalized_name(item["name"])
            ratio = SequenceMatcher(None, query_norm, candidate_norm).ratio()
            exact = query_norm == candidate_norm
            contains = bool(query_norm and (query_norm in candidate_norm or candidate_norm in query_norm))
            position_bonus = max(0.0, 0.08 - item["position"] * 0.01)
            candidate_tokens = set(_name_tokens(item["name"]))
            token_coverage = len(query_tokens & candidate_tokens) / len(query_tokens) if query_tokens else 1.0
            score = min(1.0, ratio * 0.78 + (0.18 if exact else 0.08 if contains else 0) + position_bonus)
            # Character similarity alone makes distinct nouns such as "bucket"
            # and "bunker" look deceptively close. Missing a meaningful query
            # token is an identity conflict, not a small spelling variation.
            if token_coverage < 1.0:
                score *= token_coverage
            item["tokenCoverage"] = round(token_coverage, 4)
            item["matchScore"] = round(score, 4)
        return sorted(found, key=lambda x: (-x["matchScore"], x["position"]))

    def select_identity(
        self, game_name: str, official_url: str | None = None
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        candidates = self.discover(game_name, official_url=official_url)
        best = candidates[0]
        # A valid official URL supplies the immutable Place ID. The Roblox API
        # resolution of that ID is authoritative even when the user's search
        # label intentionally expands the shorter official title for
        # disambiguation (for example "Animal Hospital Anomaly"). Keep the
        # semantic score as an audit signal, but do not reject the exact ID.
        if best.get("source") == "explicit-official-url":
            best["identitySelection"] = "explicit-place-id"
            return best, candidates
        if best["matchScore"] < 0.72:
            raise IdentityError(
                f"Top candidate confidence {best['matchScore']:.2f} is below 0.72; "
                f"review candidates in raw/identity.json",
                candidates,
            )
        if len(candidates) > 1 and best["matchScore"] - candidates[1]["matchScore"] < 0.05:
            raise IdentityError("Two Roblox candidates are too close to select safely", candidates)
        return best, candidates

    def collect(self, query: str, selected: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        universe_id = str(selected["universeId"])
        game_rows, game_source_base = self._game_rows(universe_id)
        if not game_rows:
            raise HttpError(f"Roblox returned no game for universe {universe_id}")
        game = game_rows[0]
        place_id = str(game.get("rootPlaceId") or selected["placeId"])
        votes_rows = self.http.get_json(
            f"https://games.roblox.com/v1/games/votes?universeIds={universe_id}", ttl=21600
        ).get("data", [])
        votes = votes_rows[0] if votes_rows else {}
        icons = self.http.get_json(
            "https://thumbnails.roblox.com/v1/games/icons"
            f"?universeIds={universe_id}&returnPolicy=PlaceHolder&size=512x512&format=Png&isCircular=false",
            ttl=86400,
        ).get("data", [])
        gallery_rows = self.http.get_json(
            "https://thumbnails.roblox.com/v1/games/multiget/thumbnails"
            f"?universeIds={universe_id}&countPerUniverse=10&defaults=true&size=768x432&format=Png&isCircular=false",
            ttl=86400,
        ).get("data", [])
        thumbnails = (gallery_rows[0].get("thumbnails", []) if gallery_rows else [])
        creator = game.get("creator") or {}
        developer_url = None
        developer_extra: dict[str, Any] = {}
        if creator.get("type") == "Group" and creator.get("id"):
            developer_url = f"https://www.roblox.com/communities/{creator['id']}/{slugify(creator.get('name', 'group'))}"
            try:
                developer_extra = self.http.get_json(
                    f"https://groups.roblox.com/v1/groups/{creator['id']}", ttl=604800
                )
            except HttpError:
                developer_extra = {}
        elif creator.get("id"):
            developer_url = f"https://www.roblox.com/users/{creator['id']}/profile"
        total_votes = (votes.get("upVotes") or 0) + (votes.get("downVotes") or 0)
        approval = round((votes.get("upVotes", 0) / total_votes) * 100, 1) if total_votes else None
        retrieved = utc_now()
        canonical_name = clean_roblox_display_name(game["name"])
        canonical_url = f"https://www.roblox.com/games/{place_id}/{slugify(canonical_name)}"
        facts = {
            "identity": {
                "query": query,
                "canonicalName": canonical_name,
                "currentRobloxName": game["name"],
                "slug": slugify(canonical_name),
                "platform": "Roblox",
                "placeId": place_id,
                "universeId": universe_id,
                "canonicalUrl": canonical_url,
                "matchConfidence": identity_match_confidence(selected),
                "selectionMethod": selected.get("identitySelection", "name-confidence"),
            },
            "developer": {
                "name": creator.get("name"),
                "type": creator.get("type"),
                "id": str(creator.get("id")) if creator.get("id") is not None else None,
                "url": developer_url,
                "memberCount": developer_extra.get("memberCount"),
                "verified": developer_extra.get("hasVerifiedBadge", creator.get("hasVerifiedBadge")),
            },
            "game": {
                "officialDescription": game.get("description", ""),
                "genre": game.get("genre") or game.get("genre_l1"),
                "genreL1": game.get("genre_l1"),
                "genreL2": game.get("genre_l2"),
                "price": game.get("price"),
                "maxPlayers": game.get("maxPlayers"),
                "createdAt": game.get("created"),
                "updatedAt": game.get("updated"),
                "isPlayable": game.get("isPlayable"),
                "copyingAllowed": game.get("copyingAllowed"),
            },
            "dynamicStats": {
                "retrievedAt": retrieved,
                "playing": game.get("playing"),
                "visits": game.get("visits"),
                "favorites": game.get("favoritedCount"),
                "approvalPercent": approval,
                "upVotes": votes.get("upVotes"),
                "downVotes": votes.get("downVotes"),
            },
            "officialLinks": {
                "website": None,
                "roblox": canonical_url,
                "robloxGroup": developer_url,
                "discord": None,
                "reddit": None,
                "youtube": None,
                "trailer": None,
                "x": None,
                "tiktok": None,
            },
            "codes": [],
            "gameplayFacts": [],
            "languageSignals": [],
            "media": {
                "icon": next((x.get("imageUrl") for x in icons if x.get("state") == "Completed"), None),
                "thumbnails": [x.get("imageUrl") for x in thumbnails if x.get("state") == "Completed" and x.get("imageUrl")],
                "heroImages": [x.get("imageUrl") for x in thumbnails if x.get("state") == "Completed" and x.get("imageUrl")][:5],
            },
        }
        evidence = {
            "sources": [
                {
                    "id": "src_roblox_game",
                    "url": canonical_url,
                    "title": f"{game['name']} | Play on Roblox",
                    "sourceType": "official-platform",
                    "publisher": "Roblox",
                    "retrievedAt": retrieved,
                    "httpStatus": 200,
                    "accessible": True,
                },
                {
                    "id": "src_roblox_api",
                    "url": f"{game_source_base}/{universe_id}" if game_source_base.endswith("/universes") else f"{game_source_base}?universeIds={universe_id}",
                    "title": "Roblox game details API",
                    "sourceType": "official-api",
                    "publisher": "Roblox",
                    "retrievedAt": retrieved,
                    "httpStatus": 200,
                    "accessible": True,
                },
            ],
            "claims": [
                {"field": field, "sourceIds": ["src_roblox_api"], "confidence": 1.0, "classification": "fact"}
                for field in [
                    "identity.placeId", "identity.universeId", "identity.currentRobloxName",
                    "developer.name", "game.officialDescription", "game.createdAt", "game.updatedAt",
                    "dynamicStats.playing", "dynamicStats.visits", "dynamicStats.favorites",
                ]
            ],
        }
        raw = {"game": game, "votes": votes, "icons": icons, "thumbnails": thumbnails, "developer": developer_extra}
        return facts, evidence, raw
