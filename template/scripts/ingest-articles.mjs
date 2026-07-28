#!/usr/bin/env node
// Moves every .mdx file from ARTICLES_DIR into content/<locale>/<category>/<slug>.mdx,
// reading `category` straight out of each file's metadata — no quality/topic filtering
// (that's delegated upstream to seoscout, out of scope here by design). This is the
// purely mechanical half of what used to be Part 3's "接入" step; the quality-scan
// half of Part 3 was intentionally dropped, not forgotten.
//
// Usage: npm run ingest:articles

import fs from "node:fs";
import path from "node:path";
import { resolveIntakeConfig } from "./lib/resolve-config.mjs";

const root = process.cwd();
let errors = 0;
const fail = (msg) => { console.error(`\x1b[31m✗\x1b[0m ${msg}`); errors++; };
const ok = (msg) => console.log(`\x1b[32m✓\x1b[0m ${msg}`);

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

// MDX parses the body (everything after the `export const metadata = {...}` block) as
// JSX-in-Markdown: any `<` there is read as the start of a tag unless immediately followed
// by a letter/`/`/`!`/`>`. Prose that compares numbers ("enemies <10% health") is common in
// generated game-guide content and reliably breaks the production build deep inside webpack
// with an unhelpful "Unexpected character before name" error pointing at sitemap.ts, not the
// actual file/line — this was real enough to cost a full debugging doc before its root cause
// was found. Escaping it here is unambiguous: nothing in real prose intends `<5`/`< 10`/`<=3`
// as a JSX tag, so there's no case where this fix does the wrong thing.
function escapeStrayLtInBody(source) {
  const metaMatch = source.match(/^export const metadata\s*=\s*\{[\s\S]*?^\}\s*\n?/m);
  const splitAt = metaMatch ? metaMatch[0].length : 0;
  const head = source.slice(0, splitAt);
  const body = source.slice(splitAt);
  let count = 0;
  let voidTagCount = 0;
  let autoLinkCount = 0;
  // MDX interprets CommonMark's <https://...> autolink syntax as JSX. Convert
  // it to an explicit Markdown link before any generic angle-bracket handling.
  const markdownLinkBody = body.replace(/<((?:https?:\/\/)[^\s>]+)>/gi, (_match, url) => {
    autoLinkCount++;
    return `[${url}](${url})`;
  });
  // Generated articles occasionally use a component-like Link tag. The template
  // intentionally exposes plain Markdown links, so normalize this syntax before
  // MDX compilation rather than letting it fail at runtime.
  const componentLinkBody = markdownLinkBody.replace(/<Link\s+url=["']([^"']+)["']\s*>([\s\S]*?)<\/Link>/gi, (_match, url, text) => `[${text.trim()}](${url})`);
  const mdxSafeBody = componentLinkBody.replace(/<br\s*>/gi, () => {
    voidTagCount++;
    return "<br />";
  });
  // Human-readable placeholders such as <display name> or localized
  // <nom d'affichage> begin with a letter, so the generic stray-`<` rule
  // below used to miss them and MDX parsed the prose as malformed JSX.
  // Preserve only components the template actually supports.
  const escapedUnknownTags = mdxSafeBody.replace(
    /<(?!\/?(?:Callout|br)\b)\/?[a-zA-Z][^>\n]*>/g,
    (match) => {
      count++;
      return `&lt;${match.slice(1)}`;
    },
  );
  const fixedBody = escapedUnknownTags.replace(/<(?![a-zA-Z/!>])/g, () => {
    count++;
    return "&lt;";
  });
  return { fixed: head + fixedBody, count, voidTagCount, autoLinkCount };
}

const { env } = resolveIntakeConfig(root);
const articlesDir = path.join(root, env.ARTICLES_DIR);
if (!fs.existsSync(articlesDir)) {
  console.log(`${env.ARTICLES_DIR} 不存在 —— 跳过内容接入（homepage-only 模式）。`);
  process.exit(0);
}

const planPath = path.join(root, "intake", "site-plan.json");
if (!fs.existsSync(planPath)) {
  fail("缺少 intake/site-plan.json");
  process.exit(1);
}
const plan = JSON.parse(fs.readFileSync(planPath, "utf-8"));
const allowedLocales = new Set(plan.languages || []);
const allowedCategories = new Set(
  (plan.categories || []).filter((category) => category.status === "published").map((category) => category.id),
);
const localeDirs = fs.readdirSync(articlesDir, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name);
const unexpectedLocales = localeDirs.filter((locale) => !allowedLocales.has(locale));
if (unexpectedLocales.length > 0) {
  fail(`文章包含 site-plan 未声明的语言：${unexpectedLocales.join(", ")}`);
  process.exit(1);
}

// Idempotency: content/ is a generated projection of intake/articles.  Clear it
// before every import so removed articles/categories cannot survive a rerun.
const generatedContentDir = path.join(root, "content");
fs.rmSync(generatedContentDir, { recursive: true, force: true });
let ingested = 0;

for (const locale of localeDirs) {
  const files = walkMdx(path.join(articlesDir, locale));
  for (const file of files) {
    const source = fs.readFileSync(file, "utf-8");
    const categoryMatch = source.match(/category:\s*(["'`])(.+?)\1/);
    if (!categoryMatch) {
      fail(`${path.relative(root, file)} 没有 category 字段，跳过`);
      continue;
    }
    const category = categoryMatch[2];
    if (!allowedCategories.has(category)) {
      fail(`${path.relative(root, file)} 的 category=${category} 不在 site-plan published 分类中，跳过`);
      continue;
    }
    const slug = fileNameToSlug(path.basename(file));
    const destDir = path.join(root, "content", locale, category);
    fs.mkdirSync(destDir, { recursive: true });
    const { fixed, count, voidTagCount, autoLinkCount } = escapeStrayLtInBody(source);
    fs.writeFileSync(path.join(destDir, `${slug}.mdx`), fixed);
    if (count > 0) ok(`${path.relative(root, file)} — 自动转义了 ${count} 处会导致 MDX 构建失败的裸 "<"（如 "<10%"），改成 "&lt;"`);
    if (voidTagCount > 0) ok(`${path.relative(root, file)} — 自动修复了 ${voidTagCount} 个裸 <br>，改成 MDX 合法的 <br />`);
    if (autoLinkCount > 0) ok(`${path.relative(root, file)} — 自动转换了 ${autoLinkCount} 个 <https://...> 自动链接，避免 MDX 误判为 JSX`);
    ingested++;
  }
}

ok(`${ingested} 篇文章已接入 content/（${localeDirs.length} 个语言：${localeDirs.join(", ")}）`);
if (errors > 0) process.exit(1);
