#!/usr/bin/env node

import assert from "node:assert/strict";
import { resolveSiteUrl } from "../src/config/site-url.mjs";

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
