#!/usr/bin/env node
// Fills src/locales/<locale>.json for every non-English locale that has a content/<locale>/
// directory — the multi-language counterpart to apply-content.mjs, but with zero LLM calls.
//
// Where the content comes from:
//   1. Template baseline (checked into this repo, e.g. src/locales/es.json) — the generic
//      UI chrome (nav.*/shared.*/footer.* label text) that's identical across every game
//      built on this template, translated once, ever, not per-project.
//   2. intake/site-content.<locale>.json — the per-game marketing/factual copy (site.*/
//      home.*), same schema as intake/site-content.json but already written in that
//      language. This is expected to come from whatever upstream process also decided
//      intake/site-identity.json's LANGUAGES and had seoscout write that language's
//      articles — the game-specific copy should be translated by something with full
//      context on the game, not a second, context-free pass inside this repo.
//
// If a locale is missing its intake/site-content.<locale>.json, this script fails loudly
// rather than silently shipping an English-only page under a translated URL — same
// "declared but not delivered" treatment check-intake.mjs gives a LANGUAGES mismatch.
//
// Usage: npm run apply:locales

import fs from "node:fs";
import path from "node:path";
import { resolveIntakeConfig } from "./lib/resolve-config.mjs";
import { resolveGameName, tokenValues, applyStructuredContent, substituteTokens } from "./lib/site-content.mjs";

const root = process.cwd();
const { env } = resolveIntakeConfig(root);
const GAME_NAME = resolveGameName(env);
if (!GAME_NAME || !env.OFFICIAL_GAME_URL) {
  console.error("拿不到 GAME_NAME 或 OFFICIAL_GAME_URL —— 先跑 npm run apply:content（会先做这个检查）。");
  process.exit(1);
}
const TOKEN_VALUES = tokenValues(env);

const plan = JSON.parse(fs.readFileSync(path.join(root, "intake", "site-plan.json"), "utf-8"));
const locales = plan.languages.filter((locale) => locale !== "en");

if (locales.length === 0) {
  console.log("没有非英文的 content/<locale>/ 目录 —— 无需合并多语言内容。");
  process.exit(0);
}

let errors = 0;
for (const locale of locales) {
  const structuredPath = path.join(root, "intake", `site-content.${locale}.json`);
  if (!fs.existsSync(structuredPath)) {
    console.error(
      `\x1b[31m✗\x1b[0m ${locale}：intake/site-content.${locale}.json 不存在 —— 这个语言的游戏文案没有交付，` +
        `找提供 intake/ 素材的来源补齐，不是这一步能替你生成的（这一步只做搬运，不做翻译）。`,
    );
    errors++;
    continue;
  }

  const localePath = path.join(root, "src", "locales", `${locale}.json`);
  const target = fs.existsSync(localePath) ? JSON.parse(fs.readFileSync(localePath, "utf-8")) : {};

  const structured = JSON.parse(fs.readFileSync(structuredPath, "utf-8"));
  applyStructuredContent(target, structured);

  const substituted = substituteTokens(target, TOKEN_VALUES);
  fs.writeFileSync(localePath, `${JSON.stringify(substituted, null, 2)}\n`);
  console.log(`\x1b[32m✓\x1b[0m ${locale}：intake/site-content.${locale}.json 已合并进 src/locales/${locale}.json`);
}

if (errors > 0) {
  console.log(`\n${errors} 个语言缺少 intake/site-content.<locale>.json，补齐后重跑。`);
  process.exit(1);
}
