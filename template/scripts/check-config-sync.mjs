#!/usr/bin/env node
// Verifies that the generated site is an exact projection of site-plan.json.

import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const expectedLocales = ["en", "es", "de", "fr", "ja"];
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

function missingStructure(reference, candidate, prefix = "") {
  const missing = [];
  if (Array.isArray(reference)) {
    if (!Array.isArray(candidate)) return [prefix || "(root)"];
    return missing;
  }
  if (!reference || typeof reference !== "object") return missing;
  if (!candidate || typeof candidate !== "object") return [prefix || "(root)"];
  for (const key of Object.keys(reference)) {
    const next = prefix ? `${prefix}.${key}` : key;
    if (!(key in candidate)) missing.push(next);
    else missing.push(...missingStructure(reference[key], candidate[key], next));
  }
  return missing;
}

const plan = readJson("src/config/site-plan.json");
const publicationPlan = readJson("intake/publication-plan.json");
const publicationSource = fs.existsSync(path.join(root, "src", "config", "publication.ts"))
  ? fs.readFileSync(path.join(root, "src", "config", "publication.ts"), "utf-8")
  : "";
const siteTheme = readJson("intake/site-theme.json");
const themeSource = fs.existsSync(path.join(root, "src", "config", "theme.ts"))
  ? fs.readFileSync(path.join(root, "src", "config", "theme.ts"), "utf-8")
  : "";
if (JSON.stringify(plan.languages) !== JSON.stringify(expectedLocales)) {
  fail(`site-plan 语言必须是 ${expectedLocales.join(", ")}`);
}
if (!themeSource.includes(`export const SITE_THEME = ${JSON.stringify(siteTheme.preset)}`)) {
  fail("src/config/theme.ts 未与 intake/site-theme.json 同步；先运行 npm run sync:theme");
} else {
  ok(`站点主题：${siteTheme.preset}`);
}
const publishedLocales = publicationPlan.publishedLocales || [];
if (JSON.stringify(publicationPlan.generatedLocales) !== JSON.stringify(expectedLocales)) {
  fail(`publication-plan 生成语言必须是 ${expectedLocales.join(", ")}`);
}
if (
  publishedLocales.length < 1
  || JSON.stringify(publishedLocales) !== JSON.stringify(expectedLocales.slice(0, publishedLocales.length))
) {
  fail("publication-plan 公开语言必须是固定发布顺序的前缀");
}
const expectedPublicationLine = `export const PUBLISHED_LOCALES = ${JSON.stringify(publishedLocales)} as const`;
if (!publicationSource.includes(expectedPublicationLine)) {
  fail("src/config/publication.ts 未与 intake/publication-plan.json 同步；先运行 npm run sync:publication");
} else {
  ok(`当前公开路由语言：${publishedLocales.join(", ")}`);
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
const englishMessages = readJson("src/locales/en.json");
for (const locale of expectedLocales) {
  const messages = readJson(`src/locales/${locale}.json`);
  const missingKeys = missingStructure(englishMessages, messages);
  if (missingKeys.length > 0) fail(`${locale}.json 缺少英文消息结构中的字段：${missingKeys.slice(0, 8).join(", ")}`);
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
    if (!messages[category.id]?.overviewDescription) fail(`${locale}.json 缺少 ${category.id}.overviewDescription`);
    if (locale !== "en" && messages[category.id]?.overviewDescription === englishMessages[category.id]?.overviewDescription) {
      fail(`${locale}.json 的 ${category.id}.overviewDescription 仍与英文完全相同`);
    }
    const base = path.join(localeDir, category.id);
    const files = walkMdx(base).map((file) => path.relative(base, file).replaceAll("\\", "/")).sort();
    if (locale === "en") englishTrees.set(category.id, files);
    else if (JSON.stringify(files) !== JSON.stringify(englishTrees.get(category.id) || [])) {
      fail(`${locale}/${category.id} 文章树与英文不一致`);
    }
  }
}

// Validate internal links emitted by homepage content.
const en = englishMessages;
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
