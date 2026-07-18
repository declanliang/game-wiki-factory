from __future__ import annotations

from typing import Any


NULLABLE_URL: dict[str, Any] = {"type": ["string", "null"], "format": "uri"}
ISO_639_1_CODES = [
    "aa", "ab", "ae", "af", "ak", "am", "an", "ar", "as", "av", "ay", "az",
    "ba", "be", "bg", "bh", "bi", "bm", "bn", "bo", "br", "bs",
    "ca", "ce", "ch", "co", "cr", "cs", "cu", "cv", "cy",
    "da", "de", "dv", "dz", "ee", "el", "en", "eo", "es", "et", "eu",
    "fa", "ff", "fi", "fj", "fo", "fr", "fy", "ga", "gd", "gl", "gn", "gu", "gv",
    "ha", "he", "hi", "ho", "hr", "ht", "hu", "hy", "hz",
    "ia", "id", "ie", "ig", "ii", "ik", "io", "is", "it", "iu",
    "ja", "jv", "ka", "kg", "ki", "kj", "kk", "kl", "km", "kn", "ko", "kr", "ks", "ku", "kv", "kw", "ky",
    "la", "lb", "lg", "li", "ln", "lo", "lt", "lu", "lv",
    "mg", "mh", "mi", "mk", "ml", "mn", "mr", "ms", "mt", "my",
    "na", "nb", "nd", "ne", "ng", "nl", "nn", "no", "nr", "nv", "ny",
    "oc", "oj", "om", "or", "os", "pa", "pi", "pl", "ps", "pt", "qu",
    "rm", "rn", "ro", "ru", "rw", "sa", "sc", "sd", "se", "sg", "si", "sk", "sl", "sm", "sn", "so", "sq", "sr", "ss", "st", "su", "sv", "sw",
    "ta", "te", "tg", "th", "ti", "tk", "tl", "tn", "to", "tr", "ts", "tt", "tw", "ty",
    "ug", "uk", "ur", "uz", "ve", "vi", "vo", "wa", "wo", "xh", "yi", "yo", "za", "zh", "zu",
]
DEFAULT_LANGUAGE_CODES = ["en", "es"]
MONETIZATION_LANGUAGE_CODES = ["en", "es", "de", "fr", "ja", "ko", "it", "nl"]


RESEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["officialLinks", "trailer", "codes", "gameplayFacts", "languageSignals", "moduleIdeas", "notes", "partial"],
    "properties": {
        "officialLinks": {
            "type": "object",
            "additionalProperties": False,
            "required": ["website", "discord", "reddit", "youtube", "x", "tiktok"],
            "properties": {key: NULLABLE_URL for key in ["website", "discord", "reddit", "youtube", "x", "tiktok"]},
        },
        "trailer": NULLABLE_URL,
        "codes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["code", "reward", "status", "officiallyVerified", "sourceUrls"],
                "properties": {
                    "code": {"type": "string"},
                    "reward": {"type": "string"},
                    "status": {"enum": ["verified-active", "claimed-active", "expired", "unknown"]},
                    "officiallyVerified": {"type": "boolean"},
                    "sourceUrls": {"type": "array", "items": {"type": "string", "format": "uri"}},
                },
            },
        },
        "gameplayFacts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "value", "category", "confidence", "sourceUrls"],
                "properties": {
                    "name": {"type": "string"}, "value": {"type": "string"},
                    "category": {"type": "string"}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "sourceUrls": {"type": "array", "items": {"type": "string", "format": "uri"}},
                },
            },
        },
        "languageSignals": {
            "type": "array", "maxItems": 4,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["code", "language", "reason", "confidence", "sourceUrls"],
                "properties": {
                    "code": {"type": "string"}, "language": {"type": "string"}, "reason": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "sourceUrls": {"type": "array", "items": {"type": "string", "format": "uri"}},
                },
            },
        },
        "moduleIdeas": {
            "type": "array", "maxItems": 10,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["topic", "searchIntent", "sourceUrls"],
                "properties": {
                    "topic": {"type": "string"}, "searchIntent": {"type": "string"},
                    "sourceUrls": {"type": "array", "items": {"type": "string", "format": "uri"}},
                },
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
        "partial": {"type": "boolean"},
    },
}


LANGUAGE_MARKET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["candidates", "notes", "partial"],
    "properties": {
        "candidates": {
            "type": "array",
            "minItems": 8,
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["code", "language", "recommendation", "officialSupport", "confidence", "reason", "signals"],
                "properties": {
                    "code": {"type": "string", "enum": MONETIZATION_LANGUAGE_CODES},
                    "language": {"type": "string", "minLength": 2},
                    "recommendation": {"enum": ["include", "exclude"]},
                    "officialSupport": {"type": "boolean"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string", "minLength": 20},
                    "signals": {
                        "type": "array",
                        "maxItems": 4,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["signalType", "publisher", "summary", "sourceUrls"],
                            "properties": {
                                "signalType": {"enum": ["official-localization", "creator-community", "video-community", "editorial-coverage", "search-demand", "regional-platform"]},
                                "publisher": {"type": "string", "minLength": 2},
                                "summary": {"type": "string", "minLength": 15},
                                "sourceUrls": {"type": "array", "minItems": 1, "maxItems": 6, "items": {"type": "string", "format": "uri"}},
                            },
                        },
                    },
                },
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
        "partial": {"type": "boolean"},
    },
}


HOMEPAGE_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "required": ["home", "footer", "shared", "sidebarCodes", "metadata", "links", "theme", "languages", "faviconPrompt"],
    "properties": {
        "home": {
            "type": "object", "additionalProperties": False,
            "required": ["meta", "hero", "start", "aboutGame", "finalCta"],
            "properties": {
                "meta": {"$ref": "#/$defs/meta"},
                "hero": {
                    "type": "object", "additionalProperties": False,
                    "required": ["eyebrow", "title", "description", "stats", "primaryCta", "secondaryCta", "tertiaryCta", "videoLabel"],
                    "properties": {
                        "eyebrow": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"},
                        "stats": {"type": "array", "minItems": 5, "maxItems": 5, "items": {"type": "string"}},
                        "primaryCta": {"type": "string"}, "secondaryCta": {"type": "string"},
                        "tertiaryCta": {"type": "string"}, "videoLabel": {"type": "string"},
                    },
                },
                "start": {
                    "type": "object", "additionalProperties": False, "required": ["eyebrow", "title", "cards"],
                    "properties": {
                        "eyebrow": {"type": "string"}, "title": {"type": "string"},
                        "cards": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"$ref": "#/$defs/startCard"}},
                    },
                },
                "aboutGame": {
                    "type": "object", "additionalProperties": False,
                    "required": ["title", "paragraphs", "stats", "cta"],
                    "properties": {
                        "title": {"type": "string"},
                        "paragraphs": {"type": "array", "minItems": 2, "maxItems": 3, "items": {"type": "string"}},
                        "stats": {"type": "array", "minItems": 5, "maxItems": 7, "items": {"$ref": "#/$defs/stat"}},
                        "cta": {"type": "string"},
                    },
                },
                "finalCta": {
                    "type": "object", "additionalProperties": False,
                    "required": ["title", "description", "primary", "secondary"],
                    "properties": {key: {"type": "string"} for key in ["title", "description", "primary", "secondary"]},
                },
            },
        },
        "footer": {
            "type": "object", "additionalProperties": False,
            "required": ["aboutTitle", "about", "description", "playGame", "officialDiscord", "officialYoutube", "communityTool", "privacyPolicy", "termsOfService"],
            "properties": {key: {"type": "string"} for key in ["aboutTitle", "about", "description", "playGame", "officialDiscord", "officialYoutube", "communityTool", "privacyPolicy", "termsOfService"]},
        },
        "shared": {
            "type": "object", "additionalProperties": False,
            "required": ["wikiNavigation", "activeCodes", "viewAllCodes", "home", "readMore"],
            "properties": {key: {"type": "string"} for key in ["wikiNavigation", "activeCodes", "viewAllCodes", "home", "readMore"]},
        },
        "sidebarCodes": {
            "type": "array", "minItems": 2, "maxItems": 2,
            "items": {"type": "object", "additionalProperties": False, "required": ["code", "reward", "status"], "properties": {"code": {"type": "string"}, "reward": {"type": "string"}, "status": {"enum": ["Active", "Unverified", "Unavailable"]}}},
        },
        "metadata": {
            "type": "object", "additionalProperties": False, "required": ["title", "description", "keywords"],
            "properties": {"title": {"type": "string", "maxLength": 60}, "description": {"type": "string", "minLength": 140, "maxLength": 160}, "keywords": {"type": "string", "maxLength": 100}},
        },
        "links": {
            "type": "object", "additionalProperties": False,
            "required": ["playGame", "officialDiscord", "officialYoutube", "officialTrailer", "officialX", "reddit"],
            "properties": {key: NULLABLE_URL for key in ["playGame", "officialDiscord", "officialYoutube", "officialTrailer", "officialX", "reddit"]},
        },
        "theme": {
            "type": "object", "additionalProperties": False, "required": ["defaultMode", "light", "dark", "reason", "confidence"],
            "properties": {
                "defaultMode": {"enum": ["light", "dark"]}, "light": {"$ref": "#/$defs/colors"}, "dark": {"$ref": "#/$defs/colors"},
                "reason": {"type": "string"}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "languages": {
            "type": "array", "minItems": 1, "maxItems": 4,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["rank", "code", "language", "localizedSiteName", "gameName", "basis", "sourceUrls", "confidence"],
                "properties": {
                    "rank": {"type": "integer", "minimum": 1, "maximum": 4}, "code": {"type": "string"},
                    "language": {"type": "string"}, "localizedSiteName": {"type": "string"}, "gameName": {"type": "string"},
                    "basis": {"enum": ["evidence", "inference"]}, "sourceUrls": {"type": "array", "items": {"type": "string", "format": "uri"}},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "faviconPrompt": {"type": "string", "minLength": 40},
    },
    "$defs": {
        "meta": {"type": "object", "additionalProperties": False, "required": ["title", "description"], "properties": {"title": {"type": "string", "maxLength": 60}, "description": {"type": "string", "minLength": 140, "maxLength": 160}}},
        "startCard": {"type": "object", "additionalProperties": False, "required": ["number", "title", "description"], "properties": {"number": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"}}},
        "stat": {"type": "object", "additionalProperties": False, "required": ["label", "value"], "properties": {"label": {"type": "string"}, "value": {"type": "string"}}},
        "colors": {"type": "object", "additionalProperties": False, "required": ["navTheme", "navThemeLight"], "properties": {"navTheme": {"type": "string", "pattern": "^\\d{1,3} \\d{1,3}% \\d{1,3}%$"}, "navThemeLight": {"type": "string", "pattern": "^\\d{1,3} \\d{1,3}% \\d{1,3}%$"}}},
    },
}


MODULES_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["modules"],
    "properties": {
        "modules": {
            "type": "array", "minItems": 4, "maxItems": 8,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["order", "name", "description", "href", "displayType", "highlights", "references", "confidence"],
                "properties": {
                    "order": {"type": "integer", "minimum": 1, "maximum": 8}, "name": {"type": "string"},
                    "description": {"type": "string"}, "href": {"type": "string", "pattern": "^/[a-z0-9][a-z0-9/-]*$"},
                    "displayType": {"enum": ["code-cards", "step-by-step", "tier-grid", "card-list"]},
                    "highlights": {"type": "array", "minItems": 2, "maxItems": 4, "items": {"type": "object", "additionalProperties": False, "required": ["label", "detail", "badge"], "properties": {"label": {"type": "string"}, "detail": {"type": "string"}, "badge": {"type": ["string", "null"]}}}},
                    "references": {"type": "array", "minItems": 1, "items": {"type": "string", "format": "uri"}},
                    "confidence": {"enum": ["verified", "supported", "editorial-draft"]},
                },
            },
        }
    },
}


TEMPLATE_SITE_IDENTITY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["GAME_NAME", "OFFICIAL_GAME_URL"],
    "properties": {
        "GAME_NAME": {"type": "string", "minLength": 1},
        "OFFICIAL_GAME_URL": {"type": "string", "pattern": "^https?://"},
        "DISCORD_URL": {"$ref": "#/$defs/optionalUrl"},
        "YOUTUBE_CHANNEL_URL": {"$ref": "#/$defs/optionalUrl"},
        "FANDOM_URL": {"$ref": "#/$defs/optionalUrl"},
        "YOUTUBE_VIDEO_ID": {
            "type": "string",
            "pattern": "^(?:$|[A-Za-z0-9_-]{11}|https?://(?:www\\.)?(?:youtube\\.com/(?:watch\\?v=|embed/|shorts/)|youtu\\.be/)[A-Za-z0-9_-]{11}(?:[?&#/].*)?)$",
        },
        "LANGUAGES": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {
                "type": "string",
                "enum": ISO_639_1_CODES,
            },
        },
    },
    "$defs": {
        "optionalUrl": {
            "anyOf": [
                {"const": ""},
                {"type": "string", "pattern": "^https?://"},
            ]
        }
    },
}


TEMPLATE_SITE_CONTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["site", "home"],
    "properties": {
        "site": {
            "type": "object",
            "additionalProperties": False,
            "required": ["description"],
            "properties": {
                "tagline": {"type": "string", "minLength": 3},
                "description": {"type": "string", "minLength": 80, "maxLength": 180},
                "legalNotice": {"type": "string", "minLength": 10},
                "genre": {"type": "array", "minItems": 1, "maxItems": 4, "uniqueItems": True, "items": {"type": "string", "minLength": 2}},
                "gamePlatform": {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "string", "minLength": 2}},
                "datePublished": {"type": "string", "format": "date"},
                "price": {"type": "string"},
                "priceCurrency": {"type": "string", "pattern": "^(?:$|[A-Z]{3})$"},
                "developer": {"type": "string", "minLength": 1},
            },
        },
        "home": {
            "type": "object",
            "additionalProperties": False,
            "required": ["meta", "hero", "aboutGame", "faq", "finalCta"],
            "properties": {
                "meta": {
                    "type": "object", "additionalProperties": False, "required": ["title", "description"],
                    "properties": {
                        "title": {"type": "string", "minLength": 10, "maxLength": 60},
                        "description": {"type": "string", "minLength": 80, "maxLength": 180},
                    },
                },
                "hero": {
                    "type": "object", "additionalProperties": False,
                    "required": ["eyebrow", "description", "stats"],
                    "properties": {
                        "eyebrow": {"type": "string", "minLength": 3},
                        "description": {"type": "string", "minLength": 30},
                        "stats": {"type": "array", "minItems": 1, "maxItems": 4, "items": {"$ref": "#/$defs/stat"}},
                    },
                },
                "aboutGame": {
                    "type": "object", "additionalProperties": False,
                    "required": ["title", "paragraphs", "stats"],
                    "properties": {
                        "title": {"type": "string", "minLength": 5},
                        "paragraphs": {"type": "array", "minItems": 2, "maxItems": 3, "items": {"type": "string", "minLength": 30}},
                        "stats": {"type": "array", "minItems": 1, "maxItems": 7, "items": {"$ref": "#/$defs/stat"}},
                    },
                },
                "liveTools": {
                    "type": "object", "additionalProperties": False,
                    "required": ["title", "items"],
                    "properties": {
                        "title": {"type": "string", "minLength": 3},
                        "items": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/tool"}},
                    },
                },
                "extraSections": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"$ref": "#/$defs/extraSection"},
                },
                "faq": {
                    "type": "object", "additionalProperties": False,
                    "required": ["title", "items"],
                    "properties": {
                        "title": {"type": "string", "minLength": 5},
                        "description": {"type": "string", "minLength": 10},
                        "items": {"type": "array", "minItems": 4, "maxItems": 6, "items": {"$ref": "#/$defs/faqItem"}},
                    },
                },
                "finalCta": {
                    "type": "object", "additionalProperties": False,
                    "required": ["title", "description"],
                    "properties": {
                        "title": {"type": "string", "minLength": 5},
                        "description": {"type": "string", "minLength": 20},
                    },
                },
            },
        },
    },
    "$defs": {
        "stat": {
            "type": "object", "additionalProperties": False, "required": ["value", "label"],
            "properties": {"value": {"type": "string", "minLength": 1}, "label": {"type": "string", "minLength": 1}},
        },
        "tool": {
            "type": "object", "additionalProperties": False, "required": ["title", "description", "href"],
            "properties": {
                "title": {"type": "string", "minLength": 2}, "description": {"type": "string", "minLength": 10},
                "href": {"type": "string", "pattern": "^/[a-z0-9][a-z0-9/-]*$"}, "category": {"type": "string", "minLength": 2},
            },
        },
        "extraSection": {
            "type": "object",
            "additionalProperties": False,
            "required": ["title", "items"],
            "properties": {
                "title": {"type": "string", "minLength": 3},
                "description": {"type": "string", "minLength": 10},
                "viewAllHref": {"type": "string", "pattern": "^/[a-z0-9][a-z0-9/-]*$"},
                "viewAllLabel": {"type": "string", "minLength": 3},
                "items": {
                    "type": "array",
                    "minItems": 4,
                    "maxItems": 8,
                    "items": {"$ref": "#/$defs/tool"},
                },
            },
        },
        "faqItem": {
            "type": "object", "additionalProperties": False, "required": ["question", "answer"],
            "properties": {"question": {"type": "string", "minLength": 10}, "answer": {"type": "string", "minLength": 20}},
        },
    },
}
