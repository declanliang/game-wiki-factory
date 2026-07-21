#!/usr/bin/env node
// Selects home.featured.items[] from the English article tree, then reads each
// selected article's localized metadata for every declared locale.
// deterministic rule documented in doc/新游戏上站提示词流程.md Part 3 — this used to be
// "an AI reads the rule and executes it by hand each time"; the rule itself is fully
// mechanical (no content understanding needed, just category/date/title lookups), so
// it belongs in a script, not a prompt.
//
// Rule:
//   1. Walk NAVIGATION_CONFIG in order; for each category with articles, pick one:
//      prefer a title/slug hit on a beginner-ish keyword, else the most recent by date.
//   2. If fewer than 4 items were picked (happens when there are <4 categories), top
//      up with a 2nd pick per category (same preference rule, excluding what's already
//      picked) until reaching 4 or running out of articles.
//   3. Cap at 8 items total; categories beyond the 8th (in NAVIGATION_CONFIG order)
//      don't get a pick even in step 1.
// This is deterministic — the same content/en/ tree always produces the same result.
//
// Optional override: if intake/featured-override.json exists (an array of
// {"category": "guide", "slug": "some-article"} objects), those exact articles are used
// instead of the algorithm — this is the escape hatch for "I want these specific
// articles," expressed as data instead of prose an AI would have to interpret.
//
// Usage: npm run generate:featured

import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
let errors = 0;
const fail = (msg) => { console.error(`\x1b[31m✗\x1b[0m ${msg}`); errors++; };
const ok = (msg) => console.log(`\x1b[32m✓\x1b[0m ${msg}`);
const info = (msg) => console.log(`\x1b[36mi\x1b[0m ${msg}`);

const BEGINNER_RE = /beginner|getting-started|getting started|how-to-play|how to play|guide|start|intro/i;
const MAX_ITEMS = 8;
const MIN_ITEMS = 4;
const MAX_SPOTLIGHTS = 6;
const MAX_SPOTLIGHT_ITEMS = 4;

function fileNameToSlug(fileName) {
  return fileName
    .replace(/\.mdx$/, "")
    .replace(/[^a-zA-Z0-9\-_]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

function walkMdx(dir) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walkMdx(full));
    else if (entry.name.endsWith(".mdx")) out.push(full);
  }
  return out;
}

function extractField(source, field) {
  // The closing quote must match the opening one (\1 backreference) — a naive
  // `["'\`](.+?)["'\`]` (no backreference) truncates values containing an apostrophe,
  // e.g. `title: "Animal Hospital's Mysterious Supervisor"` would stop at "Hospital".
  const m = source.match(new RegExp(`${field}:\\s*(["'\`])(.+?)\\1`));
  return m ? m[2] : "";
}

// --- 1. site-plan order (the only source of truth) ------------------------
const plan = JSON.parse(fs.readFileSync(path.join(root, "src", "config", "site-plan.json"), "utf-8"));
const categoryOrder = plan.categories
  .filter((category) => category.status === "published")
  .sort((a, b) => a.order - b.order)
  .map((category) => category.id);

if (categoryOrder.length === 0) {
  info("site-plan 里没有 published 内容分类 —— 无法生成精选内容。");
  process.exit(0);
}

// --- 2. Load every article's metadata, grouped by category, sorted newest-first ---
const articlesByCategory = new Map();
for (const category of categoryOrder) {
  const dir = path.join(root, "content", "en", category);
  const articles = walkMdx(dir).map((file) => {
    const source = fs.readFileSync(file, "utf-8");
    const slug = fileNameToSlug(path.basename(file));
    return {
      slug,
      category,
      title: extractField(source, "title") || slug,
      description: extractField(source, "description") || extractField(source, "summary") || "",
      date: extractField(source, "date"),
    };
  });
  articles.sort((a, b) =>
    (b.date || "").localeCompare(a.date || "") || a.slug.localeCompare(b.slug),
  );
  if (articles.length > 0) articlesByCategory.set(category, articles);
}

if (articlesByCategory.size === 0) {
  info("content/en/ 下没有任何文章 —— 无法生成精选内容。");
  process.exit(0);
}

function pickBest(articles, excludeSlugs) {
  const candidates = articles.filter((a) => !excludeSlugs.includes(a.slug));
  if (candidates.length === 0) return null;
  return candidates.find((a) => BEGINNER_RE.test(a.title) || BEGINNER_RE.test(a.slug)) || candidates[0]; // candidates already sorted newest-first
}

// --- 3. Optional structured override -----------------------------------------------
const overridePath = path.join(root, "intake", "featured-override.json");
let items;
if (fs.existsSync(overridePath)) {
  const override = JSON.parse(fs.readFileSync(overridePath, "utf-8"));
  info(`intake/featured-override.json 存在，使用手动指定的 ${override.length} 篇候选，不跑自动算法`);
  items = [];
  for (const { category, slug } of override) {
    const article = (articlesByCategory.get(category) || []).find((a) => a.slug === slug);
    if (!article) {
      fail(`featured-override.json 指定了 ${category}/${slug}，但 content/en/${category}/ 下找不到这篇文章`);
      continue;
    }
    items.push(article);
  }
} else {
  // --- pass 1: 1 pick per category, in NAVIGATION_CONFIG order, capped at MAX_ITEMS categories ---
  items = [];
  const usedSlugsByCategory = new Map();
  for (const category of categoryOrder) {
    if (items.length >= MAX_ITEMS) break;
    const articles = articlesByCategory.get(category);
    if (!articles) continue;
    const pick = pickBest(articles, []);
    if (pick) {
      items.push(pick);
      usedSlugsByCategory.set(category, [pick.slug]);
    }
  }
  // --- pass 2: top up to MIN_ITEMS with a 2nd pick per category, if pass 1 fell short ---
  if (items.length < MIN_ITEMS) {
    for (const category of categoryOrder) {
      if (items.length >= MIN_ITEMS || items.length >= MAX_ITEMS) break;
      const articles = articlesByCategory.get(category);
      if (!articles) continue;
      const used = usedSlugsByCategory.get(category) || [];
      const pick = pickBest(articles, used);
      if (pick) {
        items.push(pick);
        used.push(pick.slug);
        usedSlugsByCategory.set(category, used);
      }
    }
  }
}

if (errors > 0) process.exit(1);

// Category spotlights turn the homepage into a real content hub. General guides
// are already represented by Featured and the Basic Info field-guide sections;
// spotlights therefore prioritize deeper game-specific categories and only
// appear when at least two focused pages exist.
const spotlightSelections = plan.categories
  .filter((category) => category.status === "published" && category.id !== "guide")
  .sort((a, b) => a.order - b.order)
  .map((category) => ({
    category,
    articles: (articlesByCategory.get(category.id) || []).slice(0, MAX_SPOTLIGHT_ITEMS),
  }))
  .filter((entry) => entry.articles.length >= 2)
  .slice(0, MAX_SPOTLIGHTS);

// --- 4. Materialize the same selections with each locale's own metadata --------
for (const locale of plan.languages) {
  const localePath = path.join(root, "src", "locales", `${locale}.json`);
  const messages = JSON.parse(fs.readFileSync(localePath, "utf-8"));
  if (!messages.home?.featured) {
    fail(`${locale}.json 里没有 home.featured；非英语不能回退到英文精选内容`);
    continue;
  }
  const localizedItems = [];
  for (const selected of items) {
    const file = walkMdx(path.join(root, "content", locale, selected.category))
      .find((candidate) => fileNameToSlug(path.basename(candidate)) === selected.slug);
    if (!file) {
      fail(`${locale} 缺少精选文章 ${selected.category}/${selected.slug}`);
      continue;
    }
    const source = fs.readFileSync(file, "utf-8");
    const title = extractField(source, "title");
    const description = extractField(source, "description");
    if (!title || !description) {
      fail(`${locale} 精选文章 ${selected.category}/${selected.slug} 缺少本地化 title/description`);
      continue;
    }
    localizedItems.push({
      title,
      description,
      href: `/${selected.category}/${selected.slug}`,
      category: selected.category,
    });
  }
  messages.home.featured.items = localizedItems;

  const localizedSpotlights = [];
  for (const { category, articles } of spotlightSelections) {
    const spotlightItems = [];
    for (const selected of articles) {
      const file = walkMdx(path.join(root, "content", locale, selected.category))
        .find((candidate) => fileNameToSlug(path.basename(candidate)) === selected.slug);
      if (!file) {
        fail(`${locale} 缺少首页专题文章 ${selected.category}/${selected.slug}`);
        continue;
      }
      const source = fs.readFileSync(file, "utf-8");
      const title = extractField(source, "title");
      const description = extractField(source, "description");
      if (!title || !description) {
        fail(`${locale} 首页专题文章 ${selected.category}/${selected.slug} 缺少本地化 metadata`);
        continue;
      }
      spotlightItems.push({
        title,
        description,
        href: `/${selected.category}/${selected.slug}`,
        category: selected.category,
      });
    }
    const categoryLabel = category.labels?.[locale];
    const categoryDescription = category.descriptions?.[locale];
    if (!categoryLabel || !categoryDescription) {
      fail(`${locale} site-plan 分类 ${category.id} 缺少本地化 label/description`);
      continue;
    }
    const viewAllTemplate = messages.shared?.viewAllInCategory || "View all {category}";
    localizedSpotlights.push({
      title: categoryLabel,
      description: categoryDescription,
      viewAllHref: `/${category.id}`,
      viewAllLabel: viewAllTemplate.replace("{category}", categoryLabel),
      items: spotlightItems,
    });
  }
  if (localizedSpotlights.length > 0) messages.home.extraSections = localizedSpotlights;
  else delete messages.home.extraSections;
  fs.writeFileSync(localePath, `${JSON.stringify(messages, null, 2)}\n`);
  ok(`${locale} 首页已生成 ${localizedItems.length} 条精选与 ${localizedSpotlights.length} 个分类专题`);
}

if (errors > 0) process.exit(1);
