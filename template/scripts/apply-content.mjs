#!/usr/bin/env node
// Fills site.*/home.*/footer.* in en.json and the theme-color CSS variables — the
// mechanical-fill half of what used to be Part 1 + Part 2 of the prompt flow. Two
// input sources, both zero-judgment (direct substitution or straight copy, no
// generation):
//   1. Identity fields (GAME_NAME/OFFICIAL_GAME_URL/YOUTUBE_VIDEO_ID/DISCORD_URL/
//      YOUTUBE_CHANNEL_URL/FANDOM_URL) — resolved via scripts/lib/resolve-config.mjs
//      from new-site.env and/or intake/site-identity.json, whichever provides them.
//   2. intake/site-content.json — structured marketing/factual copy (hero description,
//      about-game paragraphs, FAQ, etc.) that can't be derived from identity fields
//      alone. Schema: doc/homepage-info-schema.md. If this file doesn't exist, only
//      the identity-derived fields get filled; everything else stays as __XXX__
//      placeholders (verify:site's placeholder scan will catch that, same as it
//      would for any other unfilled field).
//
// Usage: npm run apply:content

import fs from "node:fs";
import path from "node:path";
import { resolveIntakeConfig } from "./lib/resolve-config.mjs";
import { resolveGameName, tokenValues, applyStructuredContent, substituteTokens } from "./lib/site-content.mjs";

const root = process.cwd();
// Identity fields can come from new-site.env, intake/site-identity.json, or both — see
// scripts/lib/resolve-config.mjs. Neither file is required to physically exist; what matters
// is that GAME_NAME/OFFICIAL_GAME_URL resolve to something (checked right below).
const { env } = resolveIntakeConfig(root);
const GAME_NAME = resolveGameName(env);
const OFFICIAL_GAME_URL = env.OFFICIAL_GAME_URL;
if (!GAME_NAME || !OFFICIAL_GAME_URL) {
  console.error("拿不到 GAME_NAME 或 OFFICIAL_GAME_URL（new-site.env 和 intake/site-identity.json 都没提供）—— 先跑 npm run check:intake 确认必填项齐了。");
  process.exit(1);
}

const enPath = path.join(root, "src", "locales", "en.json");
const en = JSON.parse(fs.readFileSync(enPath, "utf-8"));

// --- 1. Mechanical fields from resolved identity config -----------------------
en.site.name = GAME_NAME;
en.site.shortName = GAME_NAME;
en.site.playUrl = OFFICIAL_GAME_URL;
en.home.hero.title = GAME_NAME;
en.home.hero.secondaryCtaHref = OFFICIAL_GAME_URL;
if (env.YOUTUBE_VIDEO_ID) en.home.hero.videoId = env.YOUTUBE_VIDEO_ID;
en.home.finalCta.secondaryHref = OFFICIAL_GAME_URL;
en.home.featured.title = `Featured ${GAME_NAME} Guides`;
en.home.aboutGame.title = `What is ${GAME_NAME}?`;
en.home.finalCta.title = `Ready to Play ${GAME_NAME}?`;
en.home.faq.description = `Quick answers to the most common questions about ${GAME_NAME}.`;
en.home.meta.title = `${GAME_NAME} Wiki`;
en.footer.aboutTitle = `${GAME_NAME} Wiki`;
en.footer.about = `${GAME_NAME} Wiki is an independent fan-made guide covering everything about ${GAME_NAME}.`;
en.footer.copyright = `© ${new Date().getFullYear()} ${GAME_NAME} Wiki`;
// Links stay at their REPLACE-WITH-... placeholder value when not provided — the
// footer already hides any link still pointing at that placeholder, so leaving it
// alone (rather than blanking it) is what makes that hide-if-placeholder logic work.
if (env.DISCORD_URL) en.footer.officialDiscordHref = env.DISCORD_URL;
if (env.YOUTUBE_CHANNEL_URL) en.footer.officialYoutubeHref = env.YOUTUBE_CHANNEL_URL;
if (env.FANDOM_URL) en.footer.communityToolHref = env.FANDOM_URL;

console.log("✓ 机械字段（site.*/home.hero.title+videoId/footer.* 的身份类字段）已填入");

// --- 2. Structured copy from intake/site-content.json --------------------------
const homepageInfoDir = path.join(root, env.HOMEPAGE_INFO_DIR);
const structuredPath = path.join(homepageInfoDir, "site-content.json");

if (fs.existsSync(structuredPath)) {
  const structured = JSON.parse(fs.readFileSync(structuredPath, "utf-8"));
  applyStructuredContent(en, structured);
  console.log(`✓ 结构化内容已从 ${path.relative(root, structuredPath)} 合并进 en.json`);

  // Theme color is intentionally NOT configurable per-site anymore — see the comment
  // above --nav-theme in globals.css for why. A `themeColor` key in this file (if a
  // stale intake doc still has one from before) is silently ignored, not applied.
} else {
  delete en.home.liveTools;
  delete en.home.extraSections;
  console.warn(
    `! ${path.relative(root, structuredPath)} 不存在 —— 只填了机械字段，site.description/home.hero.description/` +
      `aboutGame/faq/finalCta 等生成式文案字段仍是 __XXX__ 占位符，verify:site 会扫出来。`,
  );
}

// --- 4. Catch-all: any remaining __GAME_NAME__/__OFFICIAL_GAME_URL__/__YEAR__ token ---
// Covers templated locale fields that were not worth a dedicated line above,
// including footer and localized legal-page copy.
const TOKEN_VALUES = tokenValues(env);
const enSubstituted = substituteTokens(en, TOKEN_VALUES);

fs.writeFileSync(enPath, `${JSON.stringify(enSubstituted, null, 2)}\n`);
console.log("✓ en.json 已写入");
