#!/usr/bin/env node
// The one-command Factory template pipeline — runs every
// mechanical step in order and stops at the first failure. This is only possible
// because every step it calls is itself already a deterministic script; this file
// doesn't contain any new logic of its own, it's just the sequencing.
//
// What's NOT automated here, on purpose (still needs a human or an upstream tool):
//   - content quality/off-topic screening — delegated to seoscout, not re-checked here
//   - writing the actual marketing copy — has to already be ready-to-use in
//     intake/site-content.json by the time this runs (see Factory input contract);
//     this script only ever copies/substitutes text, it never generates any
//
// Usage: npm run launch:site [-- --skip-build]

import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const args = process.argv.slice(2);

function step(label, cmd) {
  console.log(`\n\x1b[1m▶ ${label}\x1b[0m`);
  try {
    execSync(cmd, { cwd: root, stdio: "inherit" });
  } catch {
    console.error(`\n\x1b[31m✗ 停在这一步：${label}\x1b[0m — 上面是这一步的输出，修完问题再重跑（脚本都是幂等的，不用从头开始）。`);
    process.exit(1);
  }
}

step("阶段 a 校验", "npm run check:intake");
step("同步当前公开语言", "npm run sync:publication");
step("同步站点主题预设", "npm run sync:theme");
step("文章结构预检（metadata 完整性/重复 slug/异常大文件）", "npm run validate:articles");
step("站点身份 + 首页文案（机械字段 + 结构化 intake）", "npm run apply:content");
step("素材处理（hero/favicon/manifest/主题色）", "npm run process:assets");
step("文章接入 content/", "npm run ingest:articles");
const plan = JSON.parse(fs.readFileSync(path.join(root, "intake", "site-plan.json"), "utf-8"));
const locales = plan.languages.filter((locale) => locale !== "en");
if (locales.length > 0) {
  step(`同步多语言配置（${locales.join(", ")}）`, "npm run sync:locales");
  step("合并多语言内容（intake/site-content.<locale>.json → src/locales/<locale>.json）", "npm run apply:locales");
} else {
  console.log("\n（只有 en，跳过 sync:locales / apply:locales）");
}

// Run after all structured locale content has been merged so category labels
// and internal links are projected from the final published site plan.
step("同步内容分类与首页内链", "npm run sync:categories");
step("生成五语言首页精选攻略", "npm run generate:featured");

step("全站验证", `npm run verify:site${args.includes("--skip-build") ? " -- --skip-build" : ""}`);

console.log("\n\x1b[32m✓ 全部完成，站点已生成并通过验证。\x1b[0m");
