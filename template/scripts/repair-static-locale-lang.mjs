import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outputDir = path.join(root, "out");
const localePattern = /^[a-z]{2}(?:-[A-Z]{2})?$/;

function walkHtml(directory) {
  if (!fs.existsSync(directory)) return [];
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) return walkHtml(absolute);
    return entry.isFile() && entry.name.endsWith(".html") ? [absolute] : [];
  });
}

function localeForOutput(file) {
  const relative = path.relative(outputDir, file).split(path.sep);
  const first = relative[0] || "";
  const locale = first.endsWith(".html") ? first.slice(0, -5) : first;
  return localePattern.test(locale) ? locale : "en";
}

let changed = 0;
for (const file of walkHtml(outputDir)) {
  const locale = localeForOutput(file);
  const source = fs.readFileSync(file, "utf8");
  const updated = source.replace(
    /^<!DOCTYPE html>([\s\S]*?<html\s+lang=")[^"]+(")/i,
    (_, prefix, suffix) => `${prefix}${locale}${suffix}`,
  );
  if (updated !== source) {
    fs.writeFileSync(file, updated);
    changed += 1;
  }
}

console.log(`✓ 静态 HTML lang 已同步：${changed} 个文件`);
