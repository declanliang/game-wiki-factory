#!/usr/bin/env node
// Validates the effective intake configuration right after a human/agent drops files into
// intake/ — before any AI-driven Part 0-5 conversation starts, or before npm run launch:site.
// "Effective configuration" = new-site.env (fully optional — see scripts/lib/resolve-config.mjs)
// overlaid with intake/site-identity.json, filled out with intake/ directory conventions
// (intake/hero/, intake/favicon/, intake/hero.<ext>, intake/logo.<ext>) for anything still
// unset. This script is pure reporting — resolution itself happens once, in memory, inside
// resolveIntakeConfig(), which every other script (apply-content/process-assets/ingest-articles)
// also calls, so nothing needs to be physically rewritten back into new-site.env for a
// correction (e.g. a YouTube URL normalized to a bare ID) to actually take effect.
//
// Usage: npm run check:intake

import fs from "node:fs";
import path from "node:path";
import { resolveIntakeConfig } from "./lib/resolve-config.mjs";

const root = process.cwd();

let errors = 0;
let warnings = 0;
const fail = (msg) => { console.error(`\x1b[31m✗\x1b[0m ${msg}`); errors++; };
const warn = (msg) => { console.warn(`\x1b[33m!\x1b[0m ${msg}`); warnings++; };
const ok = (msg) => console.log(`\x1b[32m✓\x1b[0m ${msg}`);
const info = (msg) => console.log(`\x1b[36mi\x1b[0m ${msg}`);

const { env, identity, resolvedByConvention, videoId } = resolveIntakeConfig(root, { warn });
const FIXED_LANGUAGES = ["en", "es", "de", "fr", "ja", "ko"];
const sitePlanPath = path.join(root, "intake", "site-plan.json");
let sitePlan = null;
if (!fs.existsSync(sitePlanPath)) {
  fail("缺少 intake/site-plan.json —— 语言和分类必须来自上游唯一规划文件");
} else {
  try {
    sitePlan = JSON.parse(fs.readFileSync(sitePlanPath, "utf-8"));
    if (sitePlan.schemaVersion !== 1) fail("intake/site-plan.json schemaVersion 必须是 1");
    if (JSON.stringify(sitePlan.languages) !== JSON.stringify(FIXED_LANGUAGES)) {
      fail(`site-plan.languages 必须是固定策略 ${FIXED_LANGUAGES.join(", ")}`);
    }
    const published = (sitePlan.categories || []).filter((category) => category.status === "published");
    if (published.length < Number(sitePlan.categoryPolicy?.minimum || 4)) {
      fail(`site-plan 只有 ${published.length} 个 published 分类，低于最低门槛`);
    } else {
      ok(`site-plan：${published.length} 个 published 分类，语言 ${sitePlan.languages.join(", ")}`);
    }
  } catch (error) {
    fail(`intake/site-plan.json 不是合法 JSON：${error.message}`);
  }
}

// --- intake/site-identity.json reporting ---------------------------------------
if (identity.parseError) fail(`intake/site-identity.json 不是合法 JSON：${identity.parseError}`);
if (identity.applied.length > 0) info(`intake/site-identity.json 已提供：${identity.applied.join(", ")}`);
if (identity.unknown.length > 0) warn(`intake/site-identity.json 里有未识别的字段（已忽略，检查是不是拼错了）：${identity.unknown.join(", ")}`);
if (!identity.exists) info("没有 intake/site-identity.json —— 身份字段（GAME_NAME 等）只能来自 new-site.env，两者都没有的话下面的必填项检查会报错");

// --- required fields -------------------------------------------------------------
for (const key of ["GAME_NAME", "OFFICIAL_GAME_URL"]) {
  if (!env[key]) fail(`${key} 是必填项，当前拿不到值 —— 填 intake/site-identity.json 或 new-site.env 二选一`);
  else ok(`${key} = ${env[key]}`);
}

// --- ARTICLES_DIR -------------------------------------------------------------
function walkMdx(dir) {
  if (!fs.existsSync(dir)) return [];
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walkMdx(full));
    else if (entry.name.endsWith(".mdx")) out.push(full);
  }
  return out;
}
const articlesAbs = path.join(root, env.ARTICLES_DIR);
const mdxFiles = walkMdx(articlesAbs);
if (!fs.existsSync(articlesAbs)) {
  fail(`ARTICLES_DIR（${env.ARTICLES_DIR}）不存在`);
} else if (mdxFiles.length === 0) {
  fail(`ARTICLES_DIR（${env.ARTICLES_DIR}）里没有任何 .mdx 文件`);
} else {
  ok(`ARTICLES_DIR（${env.ARTICLES_DIR}）— ${mdxFiles.length} 个 .mdx 文件`);
}

// --- HOMEPAGE_INFO_DIR ---------------------------------------------------------
const homepageInfoAbs = path.join(root, env.HOMEPAGE_INFO_DIR);
let homepageInfoFiles = [];
if (!fs.existsSync(homepageInfoAbs)) {
  fail(`HOMEPAGE_INFO_DIR（${env.HOMEPAGE_INFO_DIR}）不存在`);
} else {
  homepageInfoFiles = fs
    .readdirSync(homepageInfoAbs, { withFileTypes: true })
    // site-identity.json gets its own dedicated reporting above; when HOMEPAGE_INFO_DIR
    // resolves to flat "intake" (site-content.json living directly there, no subfolder)
    // it would otherwise show up twice.
    .filter((e) => e.isFile() && e.name !== ".gitkeep" && e.name !== "site-identity.json")
    .map((e) => e.name);
  if (homepageInfoFiles.length === 0) fail(`HOMEPAGE_INFO_DIR（${env.HOMEPAGE_INFO_DIR}）里没有任何素材文件`);
  else ok(`HOMEPAGE_INFO_DIR（${env.HOMEPAGE_INFO_DIR}）— ${homepageInfoFiles.length} 个文件：${homepageInfoFiles.join(", ")}`);
}

// --- legacy-template field scan in HOMEPAGE_INFO_DIR ---------------------------
const LEGACY_FIELDS = ["displayType", "sidebarCodes", "tertiaryCta", "home.start", "home.explore.modules", "themeColor"];
for (const name of homepageInfoFiles) {
  const content = fs.readFileSync(path.join(homepageInfoAbs, name), "utf-8");
  const hits = LEGACY_FIELDS.filter((f) => content.includes(f));
  if (hits.length > 0) {
    warn(`${env.HOMEPAGE_INFO_DIR}/${name} 命中旧模板专属字段名（${hits.join(", ")}）—— 这份素材可能是旧版模板的产出，部分字段会被忽略，不是致命问题但建议核实`);
  }
}

// 递归对比英文版 site-content.json 和某个语言版本的结构：字段名是否一一对应、数组长度是否
// 一致、href/category 这类不该翻译的字段值是否真的没变——只检查结构和"不该变的值"，不检查
// 可翻译文本本身的内容/质量（那是人工判断的事，脚本判断不了"翻得好不好"）。
function diffStructure(en, other, pathPrefix, issues) {
  if (Array.isArray(en)) {
    if (!Array.isArray(other)) { issues.push(`${pathPrefix}：英文是数组，译文版不是`); return; }
    if (en.length !== other.length) issues.push(`${pathPrefix}：数组长度不一致（英文 ${en.length} 条，译文 ${other.length} 条）`);
    for (let i = 0; i < Math.min(en.length, other.length); i++) diffStructure(en[i], other[i], `${pathPrefix}[${i}]`, issues);
    return;
  }
  if (en && typeof en === "object") {
    if (!other || typeof other !== "object") { issues.push(`${pathPrefix}：英文是对象，译文版缺失或类型不对`); return; }
    for (const k of Object.keys(en)) {
      const next = pathPrefix ? `${pathPrefix}.${k}` : k;
      if (!(k in other)) { issues.push(`${next}：译文版缺少这个字段`); continue; }
      if (k === "href" || k === "category") {
        if (en[k] !== other[k]) issues.push(`${next}：不该翻译的字段值不一致（英文 "${en[k]}"，译文 "${other[k]}"）`);
        continue;
      }
      diffStructure(en[k], other[k], next, issues);
    }
    for (const k of Object.keys(other)) {
      if (!(k in en)) issues.push(`${pathPrefix ? `${pathPrefix}.${k}` : k}：译文版多出这个字段，英文版没有`);
    }
  }
}

function checkLocaleContentStructure(nonEnLanguages) {
  const enPath = path.join(root, "intake", "site-content.json");
  if (!fs.existsSync(enPath)) return; // nothing to diff against
  let enStructured;
  try {
    enStructured = JSON.parse(fs.readFileSync(enPath, "utf-8"));
  } catch {
    return; // JSON 合法性已经由别的检查覆盖，这里不重复报
  }
  for (const locale of nonEnLanguages) {
    const localePath = path.join(root, "intake", `site-content.${locale}.json`);
    let localeStructured;
    try {
      localeStructured = JSON.parse(fs.readFileSync(localePath, "utf-8"));
    } catch (e) {
      fail(`intake/site-content.${locale}.json 不是合法 JSON：${e.message}`);
      continue;
    }
    const issues = [];
    diffStructure(enStructured, localeStructured, "", issues);
    if (issues.length === 0) {
      ok(`intake/site-content.${locale}.json 跟英文版结构一致（字段、数组长度、href/category 都对得上）`);
    } else {
      const shown = issues.slice(0, 8);
      const more = issues.length > shown.length ? `（还有 ${issues.length - shown.length} 条，先修这几条）` : "";
      fail(`intake/site-content.${locale}.json 跟英文版结构不一致${more}：\n    ${shown.join("\n    ")}`);
    }
  }
}

// --- 语言与分类范围：site-plan 是唯一声明源 ------------------------------
if (fs.existsSync(articlesAbs)) {
  const onDiskLocales = fs
    .readdirSync(articlesAbs, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => e.name);
  if (onDiskLocales.length > 0) {
    info(`${env.ARTICLES_DIR} 下检测到语言目录：${onDiskLocales.join(", ")}`);
  } else {
    warn(`${env.ARTICLES_DIR} 下的文章没有按语言分子目录（没有 en/ 这样的目录），如果模板要求 <locale>/<category>/ 结构，检查一下文章是不是放错层级了`);
  }

  if (sitePlan && Array.isArray(sitePlan.languages)) {
    const missing = sitePlan.languages.filter((l) => !onDiskLocales.includes(l));
    const extra = onDiskLocales.filter((l) => !sitePlan.languages.includes(l));
    if (missing.length > 0) {
      fail(`site-plan 声明了 ${missing.join(", ")}，但 ${env.ARTICLES_DIR} 下没有对应语言目录`);
    }
    if (extra.length > 0) {
      fail(`${env.ARTICLES_DIR} 下有 site-plan 未声明的语言目录：${extra.join(", ")}`);
    }
    if (missing.length === 0 && extra.length === 0) {
      ok(`site-plan 语言与 ${env.ARTICLES_DIR} 下实际目录完全一致`);
    }

    // 每个非英文语言除了文章，还要有已翻译好的游戏文案 —— apply:locales 只做机械合并，不做
    // 翻译，缺了这份文件会在那一步才报错；提前在这里报出来，不用等流程跑到 Part 4 才发现。
    if (Array.isArray(env.LANGUAGES) && JSON.stringify(env.LANGUAGES) !== JSON.stringify(sitePlan.languages)) {
      fail("site-identity.json.LANGUAGES 与 site-plan.languages 不一致");
    }
    const publishedCategories = (sitePlan.categories || []).filter((category) => category.status === "published").map((category) => category.id);
    for (const locale of sitePlan.languages) {
      const localeDir = path.join(articlesAbs, locale);
      const diskCategories = fs.existsSync(localeDir)
        ? fs.readdirSync(localeDir, { withFileTypes: true }).filter((entry) => entry.isDirectory() && walkMdx(path.join(localeDir, entry.name)).length > 0).map((entry) => entry.name).sort()
        : [];
      const missingCategories = publishedCategories.filter((category) => !diskCategories.includes(category));
      const extraCategories = diskCategories.filter((category) => !publishedCategories.includes(category));
      if (missingCategories.length || extraCategories.length) {
        fail(`${locale} 文章分类与 site-plan 不一致；缺少 ${missingCategories.join(", ") || "无"}；多出 ${extraCategories.join(", ") || "无"}`);
      }
    }

    const nonEnLanguages = sitePlan.languages.filter((l) => l !== "en");
    const missingSiteContent = nonEnLanguages.filter((l) => !fs.existsSync(path.join(root, "intake", `site-content.${l}.json`)));
    if (missingSiteContent.length > 0) {
      fail(`缺少 ${missingSiteContent.map((l) => `intake/site-content.${l}.json`).join(", ")} —— LANGUAGES 声明了这些语言，但对应的游戏文案（site.*/home.*）没有提供已翻译版本，apply:locales 会因此失败，找内容来源补齐`);
    } else if (nonEnLanguages.length > 0) {
      ok(`每个非英文语言都有对应的 intake/site-content.<locale>.json（${nonEnLanguages.join(", ")}）`);
      checkLocaleContentStructure(nonEnLanguages);
    }
  }
}

// --- YOUTUBE_VIDEO_ID ------------------------------------------------------------
if (videoId.status === "bare-id") ok(`YOUTUBE_VIDEO_ID 已经是纯 ID：${videoId.value}`);
else if (videoId.status === "extracted") info(`YOUTUBE_VIDEO_ID 检测到完整链接，已自动识别为 ID: ${videoId.value}（原值: ${videoId.original}）`);
else if (videoId.status === "invalid") fail(`YOUTUBE_VIDEO_ID 的值（${env.YOUTUBE_VIDEO_ID}）既不是纯 11 位 ID，也不是能识别的 YouTube 链接格式`);

// --- HERO_IMAGE_SOURCE / FAVICON_SET_DIR / LOGO_SOURCE: report what got resolved ---
for (const [key, value] of resolvedByConvention) {
  info(`${key} 未显式配置（或指向的文件不存在），按约定自动使用 ${value}`);
}
if (env.HERO_IMAGE_SOURCE) {
  if (fs.existsSync(path.join(root, env.HERO_IMAGE_SOURCE))) ok(`HERO_IMAGE_SOURCE（${env.HERO_IMAGE_SOURCE}）存在`);
  else warn(`HERO_IMAGE_SOURCE（${env.HERO_IMAGE_SOURCE}）指向的文件不存在，且 intake/hero/、intake/hero.* 都没有可用的候选 —— 如果确实没有这个素材可以忽略`);
} else {
  info("没有 hero 图（intake/hero/ 或 intake/hero.<ext> 都不存在）—— 首页正文不受影响，只影响 og:image/分享卡片会用模板占位图");
}

// --- FAVICON_SET_DIR: pre-generated favicon set (e.g. realfavicongenerator) -----
const FAVICON_FILES = [
  "favicon.ico",
  "favicon-16x16.png",
  "favicon-32x32.png",
  "apple-touch-icon.png",
  "android-chrome-192x192.png",
  "android-chrome-512x512.png",
  "site.webmanifest",
];
if (env.FAVICON_SET_DIR) {
  const faviconAbs = path.join(root, env.FAVICON_SET_DIR);
  if (!fs.existsSync(faviconAbs)) {
    fail(`FAVICON_SET_DIR（${env.FAVICON_SET_DIR}）不存在`);
  } else {
    const present = FAVICON_FILES.filter((f) => fs.existsSync(path.join(faviconAbs, f)));
    const missing = FAVICON_FILES.filter((f) => !present.includes(f));
    ok(`FAVICON_SET_DIR（${env.FAVICON_SET_DIR}）— 找到 ${present.length}/${FAVICON_FILES.length} 个已知文件：${present.join(", ")}`);
    if (missing.length > 0) warn(`FAVICON_SET_DIR 缺这几个文件：${missing.join(", ")} —— 对应槽位会保留模板占位图，如果是有意只换部分尺寸可以忽略`);
  }
} else if (env.LOGO_SOURCE) {
  if (fs.existsSync(path.join(root, env.LOGO_SOURCE))) ok(`LOGO_SOURCE（${env.LOGO_SOURCE}）存在`);
  else warn(`LOGO_SOURCE（${env.LOGO_SOURCE}）指向的文件不存在 —— 如果确实没有这个素材可以忽略`);
} else {
  info("没有 favicon 素材（intake/favicon/ 或 intake/logo.<ext> 都不存在）—— process:assets 会自动用游戏名首字母生成一套图标");
}

console.log(`\n${errors} error(s), ${warnings} warning(s).`);
process.exit(errors > 0 ? 1 : 0);
