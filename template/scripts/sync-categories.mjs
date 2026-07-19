#!/usr/bin/env node
// Materializes the upstream site plan.  It never scans content/ to invent
// categories and never patches TypeScript source code.

import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const source = path.join(root, "intake", "site-plan.json");
const target = path.join(root, "src", "config", "site-plan.json");
const FIXED_LANGUAGES = ["en", "es", "de", "fr", "ja", "ko"];

function fail(message) {
  console.error(`\x1b[31m✗\x1b[0m ${message}`);
  process.exit(1);
}

if (!fs.existsSync(source)) fail("缺少 intake/site-plan.json；分类必须由上游 Basic Info / planner 提供");
let plan;
try {
  plan = JSON.parse(fs.readFileSync(source, "utf-8"));
} catch (error) {
  fail(`intake/site-plan.json 不是合法 JSON：${error.message}`);
}

if (plan.schemaVersion !== 1 || !Array.isArray(plan.categories)) fail("site-plan schemaVersion/categories 不合法");
if (JSON.stringify(plan.languages) !== JSON.stringify(FIXED_LANGUAGES)) {
  fail(`site-plan languages 必须是固定策略 ${FIXED_LANGUAGES.join(", ")}`);
}
const ids = plan.categories.map((category) => category.id);
if (new Set(ids).size !== ids.length) fail("site-plan categories 包含重复 id");
for (const category of plan.categories) {
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(category.id || "")) fail(`非法分类 id：${category.id}`);
  if (!category.labels || FIXED_LANGUAGES.some((locale) => !category.labels[locale])) {
    fail(`分类 ${category.id} 缺少六语言 labels`);
  }
}
const published = plan.categories.filter((category) => category.status === "published");
if (published.length < Number(plan.categoryPolicy?.minimum || 4)) {
  fail(`site-plan 只有 ${published.length} 个 published 分类，低于质量门槛`);
}

fs.mkdirSync(path.dirname(target), { recursive: true });
fs.writeFileSync(target, `${JSON.stringify(plan, null, 2)}\n`);

// Category labels/list-page headings are deterministic plan data.  Game copy
// is merged later by apply-locales.mjs.
for (const locale of FIXED_LANGUAGES) {
  const localePath = path.join(root, "src", "locales", `${locale}.json`);
  const messages = fs.existsSync(localePath) ? JSON.parse(fs.readFileSync(localePath, "utf-8")) : {};
  messages.nav ||= {};
  for (const category of published) {
    const label = category.labels[locale] || category.labels.en;
    messages.nav[category.id] = label;
    messages[category.id] = {
      overviewTitle: label,
      overviewDescription: category.description || "",
    };
  }
  fs.writeFileSync(localePath, `${JSON.stringify(messages, null, 2)}\n`);
}

console.log(`\x1b[32m✓\x1b[0m site-plan 已同步：${published.map((item) => item.id).join(", ")}`);
