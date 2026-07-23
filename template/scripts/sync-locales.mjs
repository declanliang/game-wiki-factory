#!/usr/bin/env node
// Locale wiring is fixed in the clean template.  This command validates the
// site-plan contract and creates missing message shells; it does not patch code.

import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const expected = ["en", "es", "de", "fr", "ja"];
const planPath = path.join(root, "intake", "site-plan.json");
if (!fs.existsSync(planPath)) {
  console.error("缺少 intake/site-plan.json");
  process.exit(1);
}
const plan = JSON.parse(fs.readFileSync(planPath, "utf-8"));
if (JSON.stringify(plan.languages) !== JSON.stringify(expected)) {
  console.error(`site-plan languages 必须是 ${expected.join(", ")}`);
  process.exit(1);
}
for (const locale of expected) {
  const localePath = path.join(root, "src", "locales", `${locale}.json`);
  if (!fs.existsSync(localePath)) fs.writeFileSync(localePath, "{}\n");
}
console.log(`\x1b[32m✓\x1b[0m 固定语言配置已就绪：${expected.join(", ")}`);
