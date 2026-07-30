// Shared by check-intake.mjs / apply-content.mjs / process-assets.mjs / ingest-articles.mjs.
//
// `new-site.env` used to be the only place these scripts read from, which meant a human had
// to keep it in sync with whatever was actually dropped in intake/ even when every field was
// 100% predictable from convention (identity fields already duplicated in
// intake/site-identity.json; asset paths already fixed by where the files were placed). This
// module makes new-site.env entirely optional: everything it can hold is now resolved from
// convention first, with an explicit non-empty value in new-site.env (if the file exists)
// acting only as an override for the rare non-standard case.
//
// Priority per field: explicit new-site.env value (if non-empty) > intake/ convention > unset.

import fs from "node:fs";
import path from "node:path";

const IMAGE_EXTS = ["jpg", "jpeg", "png", "webp", "gif", "svg", "ico"];
const STRING_IDENTITY_KEYS = ["GAME_NAME", "OFFICIAL_GAME_URL", "DISCORD_URL", "YOUTUBE_CHANNEL_URL", "FANDOM_URL", "YOUTUBE_VIDEO_ID"];
// LANGUAGES is array-typed (unlike the other identity fields, which are all plain strings) —
// included here so applyIdentityJson's "unknown key" scan recognizes it, but it's validated
// and applied by its own branch below, not the generic string-field loop.
const IDENTITY_KEYS = [...STRING_IDENTITY_KEYS, "LANGUAGES"];
const IDENTITY_URL_FIELDS = new Set(["OFFICIAL_GAME_URL", "DISCORD_URL", "YOUTUBE_CHANNEL_URL", "FANDOM_URL"]);

export function loadEnvFile(p) {
  const env = {};
  if (!fs.existsSync(p)) return env;
  for (const line of fs.readFileSync(p, "utf-8").split(/\r\n|\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    env[line.slice(0, eq).trim()] = line.slice(eq + 1).trim();
  }
  return env;
}

function firstImageIn(dir) {
  if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) return null;
  const files = fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isFile())
    .map((e) => e.name)
    .filter((name) => IMAGE_EXTS.includes((name.split(".").pop() ?? "").toLowerCase()))
    .sort();
  return files.length > 0 ? files[0] : null;
}

function firstFileWithStem(dir, stem) {
  if (!fs.existsSync(dir)) return null;
  const match = fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isFile())
    .map((e) => e.name)
    .find((name) => name.replace(/\.[^.]+$/, "") === stem && IMAGE_EXTS.includes((name.split(".").pop() ?? "").toLowerCase()));
  return match ?? null;
}

// intake/site-identity.json's identity fields, applied on top of new-site.env (JSON wins
// when both are present — it's the fresher, purpose-built source). Same URL-shape guard as
// check-intake.mjs: a value like "未找到" for a link field is treated as not-provided rather
// than written through as a broken literal href.
function applyIdentityJson(root, env, { warn } = {}) {
  const identityPath = path.join(root, "intake", "site-identity.json");
  if (!fs.existsSync(identityPath)) return { applied: [], rejected: [], unknown: [], parseError: null, exists: false };
  let identity;
  try {
    identity = JSON.parse(fs.readFileSync(identityPath, "utf-8"));
  } catch (e) {
    return { applied: [], rejected: [], unknown: [], parseError: e.message, exists: true };
  }
  const applied = [];
  const rejected = [];
  for (const key of STRING_IDENTITY_KEYS) {
    const value = identity[key];
    if (typeof value !== "string" || !value.trim()) continue;
    const trimmed = value.trim();
    if (IDENTITY_URL_FIELDS.has(key) && !/^https?:\/\//i.test(trimmed)) {
      rejected.push({ key, value: trimmed });
      warn?.(`intake/site-identity.json 的 ${key}（"${trimmed}"）不是一个 http(s) 链接，当作"没有这个链接"处理`);
      continue;
    }
    env[key] = trimmed;
    applied.push(key);
  }
  // LANGUAGES declares the intended language scope so check-intake.mjs can cross-check it
  // against intake/articles/<locale>/ and flag a mismatch as a delivery gap (not a template
  // gap) — it does NOT drive any script's actual behavior, which stays purely folder-based
  // (see the comment in resolveIntakeConfig below), so an omitted/invalid value here changes
  // nothing except losing that cross-check.
  if (identity.LANGUAGES !== undefined) {
    if (Array.isArray(identity.LANGUAGES) && identity.LANGUAGES.every((l) => typeof l === "string")) {
      const langs = identity.LANGUAGES.map((l) => l.trim().toLowerCase()).filter(Boolean);
      if (langs.length > 0) {
        env.LANGUAGES = langs;
        applied.push("LANGUAGES");
      }
    } else {
      rejected.push({ key: "LANGUAGES", value: identity.LANGUAGES });
      warn?.(`intake/site-identity.json 的 LANGUAGES 必须是字符串数组（如 ["en", "es"]），当前值不是，已忽略`);
    }
  }
  const unknown = Object.keys(identity).filter((k) => !IDENTITY_KEYS.includes(k));
  return { applied, rejected, unknown, parseError: null, exists: true };
}

const YOUTUBE_URL_PATTERNS = [/(?:youtube\.com\/watch\?v=|youtube\.com\/embed\/|youtube\.com\/shorts\/|youtu\.be\/)([A-Za-z0-9_-]{11})/];

// Every script that reads YOUTUBE_VIDEO_ID needs the bare 11-char ID (it goes straight into
// an embed URL) — normalizing here, once, in memory means apply-content.mjs gets the right
// value regardless of whether the raw value came from new-site.env or site-identity.json, and
// regardless of whether check:intake ran first (it used to be the only place this happened,
// by physically rewriting new-site.env before anything else ran).
function normalizeYoutubeVideoId(raw) {
  if (!raw) return { value: "", status: "empty" };
  if (/^[A-Za-z0-9_-]{11}$/.test(raw)) return { value: raw, status: "bare-id" };
  for (const re of YOUTUBE_URL_PATTERNS) {
    const m = raw.match(re);
    if (m) return { value: m[1], status: "extracted", original: raw };
  }
  return { value: raw, status: "invalid" };
}

function normalizeYoutubeChannelUrl(raw) {
  if (!raw) return { value: "", status: "empty" };
  let parsed;
  try {
    parsed = new URL(decodeURIComponent(raw.trim()));
  } catch {
    return { value: raw, status: "invalid" };
  }
  if (!/^www\.youtube\.com$|^youtube\.com$/i.test(parsed.hostname)) return { value: raw, status: "invalid" };
  const parts = parsed.pathname.split("/").filter(Boolean);
  if (!parts.length || /^(watch|embed|shorts|live)$/i.test(parts[0])) return { value: raw, status: "invalid" };
  let channel = "";
  if (parts[0].startsWith("@")) channel = parts[0];
  else if (/^(channel|c|user)$/i.test(parts[0]) && parts[1]) channel = `${parts[0]}/${parts[1]}`;
  if (!channel) return { value: raw, status: "invalid" };
  return { value: `https://www.youtube.com/${channel}`, status: "normalized", original: raw };
}

/**
 * Resolves the effective intake configuration: new-site.env (if present) overlaid with
 * intake/site-identity.json identity fields, then filled out with intake/ directory
 * conventions for anything still unset. Returns a flat env-shaped object plus metadata about
 * what came from where, so callers (check-intake.mjs especially) can report it clearly.
 */
export function resolveIntakeConfig(root, { warn } = {}) {
  const env = loadEnvFile(path.join(root, "new-site.env"));
  // new-site.env is a flat key=value file, so a LANGUAGES override set there (rather than as
  // a real JSON array in site-identity.json) arrives as a comma-separated string — normalize
  // both sources to the same array shape before applyIdentityJson potentially overwrites it.
  if (typeof env.LANGUAGES === "string") {
    env.LANGUAGES = env.LANGUAGES.split(",").map((l) => l.trim().toLowerCase()).filter(Boolean);
  }
  const identity = applyIdentityJson(root, env, { warn });

  env.ARTICLES_DIR ||= "intake/articles";

  const resolvedByConvention = [];

  // site-content.json: flat intake/site-content.json is the primary (and now the only
  // documented) convention, sibling to site-identity.json, no subfolder needed. The nested
  // intake/homepage-info/site-content.json path is kept working purely so older projects
  // that already used that layout don't break — new projects shouldn't create this folder.
  // Same existence check as HERO_IMAGE_SOURCE/FAVICON_SET_DIR below: a stale explicit value
  // (e.g. a new-site.env left over from before a project migrated to the flat layout,
  // pointing at a homepage-info/ folder that's since been deleted) must fall through to
  // convention instead of hard-failing — an override only counts if it actually resolves.
  if (!env.HOMEPAGE_INFO_DIR || !fs.existsSync(path.join(root, env.HOMEPAGE_INFO_DIR))) {
    const flatExists = fs.existsSync(path.join(root, "intake", "site-content.json"));
    env.HOMEPAGE_INFO_DIR = flatExists ? "intake" : "intake/homepage-info";
    if (flatExists) resolvedByConvention.push(["HOMEPAGE_INFO_DIR", "intake"]);
  }

  // Hero: explicit HERO_IMAGE_SOURCE wins if it points at a real file; else
  // intake/hero/<first image> (a directory of candidates); else intake/hero.<ext>.
  if (!env.HERO_IMAGE_SOURCE || !fs.existsSync(path.join(root, env.HERO_IMAGE_SOURCE))) {
    const heroDirFile = firstImageIn(path.join(root, "intake", "hero"));
    const heroFlatFile = firstFileWithStem(path.join(root, "intake"), "hero");
    const resolved = heroDirFile ? path.posix.join("intake", "hero", heroDirFile) : heroFlatFile ? path.posix.join("intake", heroFlatFile) : null;
    if (resolved) {
      env.HERO_IMAGE_SOURCE = resolved;
      resolvedByConvention.push(["HERO_IMAGE_SOURCE", resolved]);
    } else if (!env.HERO_IMAGE_SOURCE) {
      delete env.HERO_IMAGE_SOURCE;
    }
  }

  // Favicon: explicit FAVICON_SET_DIR/LOGO_SOURCE win if they point at something real;
  // else intake/favicon/ (a full pre-generated set); else intake/logo.<ext> (single source).
  const faviconSetValid = env.FAVICON_SET_DIR && fs.existsSync(path.join(root, env.FAVICON_SET_DIR));
  const logoSourceValid = env.LOGO_SOURCE && fs.existsSync(path.join(root, env.LOGO_SOURCE));
  if (!faviconSetValid && !logoSourceValid) {
    const faviconDir = path.join(root, "intake", "favicon");
    if (fs.existsSync(faviconDir) && fs.statSync(faviconDir).isDirectory()) {
      env.FAVICON_SET_DIR = "intake/favicon";
      delete env.LOGO_SOURCE;
      resolvedByConvention.push(["FAVICON_SET_DIR", "intake/favicon"]);
    } else {
      const logoFile = firstFileWithStem(path.join(root, "intake"), "logo");
      if (logoFile) {
        env.LOGO_SOURCE = path.posix.join("intake", logoFile);
        delete env.FAVICON_SET_DIR;
        resolvedByConvention.push(["LOGO_SOURCE", env.LOGO_SOURCE]);
      } else {
        if (!env.FAVICON_SET_DIR) delete env.FAVICON_SET_DIR;
        if (!env.LOGO_SOURCE) delete env.LOGO_SOURCE;
      }
    }
  }

  const videoId = normalizeYoutubeVideoId(env.YOUTUBE_VIDEO_ID || "");
  if (videoId.status === "bare-id" || videoId.status === "extracted") env.YOUTUBE_VIDEO_ID = videoId.value;
  const channelUrl = normalizeYoutubeChannelUrl(env.YOUTUBE_CHANNEL_URL || "");
  if (channelUrl.status === "normalized") env.YOUTUBE_CHANNEL_URL = channelUrl.value;

  return { env, identity, resolvedByConvention, videoId, channelUrl };
}
