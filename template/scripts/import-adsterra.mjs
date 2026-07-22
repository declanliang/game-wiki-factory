import fs from "node:fs";
import path from "node:path";

const sourcePath = path.join(process.cwd(), "ad.txt");
const envPath = path.join(process.cwd(), ".env.local");
if (!fs.existsSync(sourcePath)) throw new Error(`Missing ${sourcePath}`);
const source = fs.readFileSync(sourcePath, "utf8").replace(/\r\n/g, "\n");
const placements = [
  ["Native Banner", "AD_NATIVE_BANNER_B64", null], ["Banner 468x60", "AD_BANNER_468X60_B64", [468, 60]],
  ["Banner 300x250", "AD_BANNER_300X250_B64", [300, 250]], ["Banner 160x300", "AD_SIDEBAR_160X300_B64", [160, 300]],
  ["Banner 160x600", "AD_SIDEBAR_160X600_B64", [160, 600]], ["Banner 320x50", "AD_MOBILE_320X50_B64", [320, 50]],
  ["Banner 728x90", "AD_BANNER_728X90_B64", [728, 90]],
];
const snippets = new Map();
for (let index = 0; index < placements.length; index += 1) {
  const [label, envName, size] = placements[index];
  const start = source.indexOf(label);
  if (start < 0) throw new Error(`Missing Adsterra section: ${label}`);
  const contentStart = start + label.length;
  const nextStarts = placements.slice(index + 1).map(([nextLabel]) => source.indexOf(nextLabel, contentStart)).filter((position) => position >= 0);
  const snippet = source.slice(contentStart, nextStarts.length ? Math.min(...nextStarts) : source.length).trim();
  if (!snippet.includes("<script")) throw new Error(`${label} has no script tag`);
  if (size) {
    const [width, height] = size;
    if (!new RegExp(`['\"]width['\"]\\s*:\\s*${width}`).test(snippet) || !new RegExp(`['\"]height['\"]\\s*:\\s*${height}`).test(snippet)) throw new Error(`${label} dimensions do not match ${width}x${height}`);
  } else if (!/container-[a-z0-9]+/i.test(snippet)) throw new Error("Native Banner container is missing");
  snippets.set(envName, snippet);
}
let envText = fs.existsSync(envPath) ? fs.readFileSync(envPath, "utf8").replace(/\r\n/g, "\n") : "";
for (const [, envName] of placements) {
  const line = `${envName}=${Buffer.from(snippets.get(envName), "utf8").toString("base64")}`;
  const expression = new RegExp(`^${envName}=.*$`, "m");
  envText = expression.test(envText) ? envText.replace(expression, line) : `${envText.trimEnd()}\n${line}\n`;
}
fs.writeFileSync(envPath, envText.replace(/^\n+/, ""), "utf8");
console.log(`Imported ${placements.length} isolated Adsterra units into .env.local (values hidden).`);
