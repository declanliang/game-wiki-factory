#!/usr/bin/env node
// Verifies that the generated site is an exact projection of site-plan.json.

import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const expectedLocales = ["en", "es", "de", "fr", "ja", "ko"];
let errors = 0;
let warnings = 0;
const fail = (message) => { console.error(`\x1b[31m✗\x1b[0m ${message}`); errors++; };
const warn = (message) => { console.warn(`\x1b[33m!\x1b[0m ${message}`); warnings++; };
const ok = (message) => console.log(`\x1b[32m✓\x1b[0m ${message}`);

function readJson(relativePath) {
  try {
    return JSON.parse(fs.readFileSync(path.join(root, relativePath), "utf-8"));
  } catch (error) {
    fail(`${relativePath} 无法读取：${error.message}`);
    return {};
  }
}

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

const plan = readJson("src/config/site-plan.json");
if (JSON.stringify(plan.languages) !== JSON.stringify(expectedLocales)) {
  fail(`site-plan 语言必须是 ${expectedLocales.join(", ")}`);
}
const categories = (plan.categories || [])
  .filter((category) => category.status === "published")
  .sort((a, b) => a.order - b.order);
const categoryIds = categories.map((category) => category.id);
if (new Set(categoryIds).size !== categoryIds.length) fail("site-plan 有重复 published 分类");
if (categories.length < Number(plan.categoryPolicy?.minimum ?? 1)) fail("published 分类低于 site-plan 最低门槛");
else ok(`site-plan 分类：${categoryIds.join(", ")}`);

const contentRoot = path.join(root, "content");
const diskLocales = fs.existsSync(contentRoot)
  ? fs.readdirSync(contentRoot, { withFileTypes: true }).filter((entry) => entry.isDirectory()).map((entry) => entry.name).sort()
  : [];
const expectedSorted = [...expectedLocales].sort();
if (JSON.stringify(diskLocales) !== JSON.stringify(expectedSorted)) {
  fail(`content 语言目录不一致；期望 ${expectedSorted.join(", ")}，实际 ${diskLocales.join(", ")}`);
}

const englishTrees = new Map();
for (const locale of expectedLocales) {
  const messages = readJson(`src/locales/${locale}.json`);
  const localeDir = path.join(contentRoot, locale);
  const diskCategories = fs.existsSync(localeDir)
    ? fs.readdirSync(localeDir, { withFileTypes: true }).filter((entry) => entry.isDirectory()).map((entry) => entry.name).sort()
    : [];
  const expectedCategories = [...categoryIds].sort();
  if (JSON.stringify(diskCategories) !== JSON.stringify(expectedCategories)) {
    fail(`${locale} 分类目录不一致；期望 ${expectedCategories.join(", ")}，实际 ${diskCategories.join(", ")}`);
  }
  for (const category of categories) {
    if (!messages.nav?.[category.id]) fail(`${locale}.json 缺少 nav.${category.id}`);
    if (!messages[category.id]?.overviewTitle) fail(`${locale}.json 缺少 ${category.id}.overviewTitle`);
    const base = path.join(localeDir, category.id);
    const files = walkMdx(base).map((file) => path.relative(base, file).replaceAll("\\", "/")).sort();
    if (locale === "en") englishTrees.set(category.id, files);
    else if (JSON.stringify(files) !== JSON.stringify(englishTrees.get(category.id) || [])) {
      fail(`${locale}/${category.id} 文章树与英文不一致`);
    }
  }
}

// Validate internal links emitted by homepage content.
const en = readJson("src/locales/en.json");
function collectHrefs(value, out = []) {
  if (typeof value === "string" && value.startsWith("/") && !value.startsWith("//")) out.push(value);
  else if (Array.isArray(value)) value.forEach((item) => collectHrefs(item, out));
  else if (value && typeof value === "object") Object.values(value).forEach((item) => collectHrefs(item, out));
  return out;
}
function fileNameToSlug(fileName) {
  return fileName.replace(/\.mdx$/, "").replace(/[^a-zA-Z0-9\-_]/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
}
const staticPages = new Set(["/", "/about", "/privacy-policy", "/terms-of-service", "/copyright"]);
for (const href of new Set(collectHrefs(en))) {
  if (staticPages.has(href)) continue;
  const [category, ...segments] = href.split("/").filter(Boolean);
  if (!categoryIds.includes(category)) {
    fail(`en.json 内链 ${href} 指向未发布分类`);
    continue;
  }
  if (segments.length === 0) continue;
  const slugs = (englishTrees.get(category) || []).map((file) => fileNameToSlug(file).replace(/\.mdx$/, ""));
  if (!slugs.includes(segments.join("/"))) warn(`en.json 内链 ${href} 未匹配英文文章（检查精选内容是否过期）`);
}

console.log(`\n${errors} error(s), ${warnings} warning(s).`);
process.exit(errors > 0 ? 1 : 0);
