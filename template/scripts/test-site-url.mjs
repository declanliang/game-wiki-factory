#!/usr/bin/env node

import assert from "node:assert/strict";
import { resolveDeploymentSiteUrl, resolveSiteUrl } from "../src/config/site-url.mjs";
import { absoluteLocalizedUrl, localizedPathname, normalizePathname } from "../src/config/site-path.mjs";

const cases = [
  ["game.example.com", "https://game.example.com"],
  ["https://game.example.com", "https://game.example.com"],
  ["https://game.example.com/", "https://game.example.com"],
  ["  game.example.com  ", "https://game.example.com"],
  ["https://game.example.com/path?x=1#hash", "https://game.example.com"],
  ["http://localhost:3000", "http://localhost:3000"],
  [undefined, "https://example.com"],
];

for (const [input, expected] of cases) {
  assert.equal(resolveSiteUrl(input), expected);
}
const invalidCases = ["ftp://game.example.com", "mailto:user@example.com", "not a valid host", "://bad"];
for (const invalid of invalidCases) {
  assert.throws(() => resolveSiteUrl(invalid), /NEXT_PUBLIC_SITE_URL/);
}

console.log(`site URL normalization: ${cases.length} valid and ${invalidCases.length} invalid cases passed`);

assert.equal(normalizePathname("//guide//tips/"), "/guide/tips");
assert.equal(localizedPathname("/guide/tips", "en"), "/en/guide/tips");
assert.equal(localizedPathname("/guide/tips", "es"), "/es/guide/tips");
assert.equal(localizedPathname("/", "ja"), "/ja");
assert.equal(absoluteLocalizedUrl("https://game.example.com/", "/guide", "de"), "https://game.example.com/de/guide");
assert.equal(resolveDeploymentSiteUrl({ VERCEL_PROJECT_PRODUCTION_URL: "game.vercel.app" }), "https://game.vercel.app");
assert.equal(resolveDeploymentSiteUrl({ NEXT_PUBLIC_SITE_URL: "custom.wiki", VERCEL_PROJECT_PRODUCTION_URL: "game.vercel.app" }), "https://custom.wiki");
assert.throws(() => normalizePathname("https://other.example.com/guide"), /site-relative/);
console.log("localized site paths: canonical path and double-slash cases passed");
