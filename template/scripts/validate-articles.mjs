#!/usr/bin/env node
// Preflight checks for intake/articles/ — runs before any generation step touches the
// repo, so a bad file gets reported with useful context instead of failing deep inside
// webpack after apply-content/process-assets/sync-categories have already run. (The
// original motivating case: a stray "<10%" broke `next build` with an error pointing at
// sitemap.ts, nowhere near the actual file — ingest-articles.mjs now auto-fixes that one
// specific pattern defensively; the structural issues below aren't auto-fixable, they
// need a human decision, so they're caught here instead.)
//
// Usage: npm run validate:articles

import fs from "node:fs";
import path from "node:path";
import { resolveIntakeConfig } from "./lib/resolve-config.mjs";

const root = process.cwd();
let errors = 0;
let warnings = 0;
const fail = (msg) => { console.error(`\x1b[31m✗\x1b[0m ${msg}`); errors++; };
const warn = (msg) => { console.warn(`\x1b[33m!\x1b[0m ${msg}`); warnings++; };
const ok = (msg) => console.log(`\x1b[32m✓\x1b[0m ${msg}`);

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

// Same slug derivation ingest-articles.mjs uses — has to match exactly, since the whole
// point of the duplicate check below is predicting the same destination path it computes.
function fileNameToSlug(fileName) {
  return fileName
    .replace(/\.mdx$/, "")
    .replace(/[^a-zA-Z0-9\-_]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

function articleBody(source) {
  const metaMatch = source.match(/^export const metadata\s*=\s*\{[\s\S]*?^\}\s*\n?/m);
  return metaMatch ? source.slice(metaMatch[0].length).trim() : "";
}

const PLACEHOLDER_DESTINATIONS = new Set(["url", "link", "todo", "#", "example.com"]);

function placeholderMarkdownDestination(body) {
  let fenced = false;
  const lines = body.split(/\r?\n/);
  for (const [index, line] of lines.entries()) {
    if (/^\s*```/.test(line)) {
      fenced = !fenced;
      continue;
    }
    if (fenced) continue;
    for (const match of line.matchAll(/\[[^\]]+\]\(([^\s)]+)(?:\s+"[^"]*")?\)/g)) {
      const destination = match[1].trim().toLocaleLowerCase();
      if (PLACEHOLDER_DESTINATIONS.has(destination)) return { line: index + 1, destination: match[1] };
    }
  }
  return null;
}

function headingSignature(body) {
  return [...body.matchAll(/^(#{2,6})[ \t]+\S/gm)].map((match) => match[1]);
}

function calloutSignature(body) {
  return [...body.matchAll(/<Callout\b[^>]*>|<\/Callout>/g)].map((match) =>
    match[0].startsWith("</") ? "close" : "open",
  );
}

function balancedCallouts(signature) {
  let depth = 0;
  for (const token of signature) {
    depth += token === "open" ? 1 : -1;
    if (depth < 0) return false;
  }
  return depth === 0;
}

const STRUCTURAL_PATTERNS = {
  "列表项": /^\s*[-*+]\s+\S/gm,
  "编号项": /^\s*\d+[.)]\s+\S/gm,
  "表格行": /^\s*\|.*\|\s*$/gm,
  // Heading count/levels are already compared separately. Treat only a fully
  // bold standalone question as a formatting marker; otherwise a normal
  // question heading or a bold lead-in followed by prose becomes a false
  // translation-truncation signal.
  "格式化问题": /^\s*\*\*[^\n]*(?:\?|？)\*\*\s*$/gm,
};

function countMatches(body, pattern) {
  return (body.match(pattern) || []).length;
}

const REQUIRED_FIELDS = ["title", "description", "category", "date"];
const ALLOWED_FIELDS = new Set([
  "title",
  "description",
  "category",
  "date",
  "lastModified",
  "image",
  "imageAlt",
  "badge",
  "summary",
  "relatedVideo",
]);

function parseMetadata(metaBody, rel) {
  const values = new Map();
  const lines = metaBody.split(/\r?\n/);
  for (const [index, rawLine] of lines.entries()) {
    const line = rawLine.trim();
    if (!line) continue;
    const relatedVideoMatch = line.match(/^relatedVideo\s*:\s*(\{.*\})\s*,?$/);
    if (relatedVideoMatch) {
      if (values.has("relatedVideo")) {
        fail(`${rel}：metadata 字段 relatedVideo 重复出现`);
        continue;
      }
      try {
        const value = JSON.parse(relatedVideoMatch[1]);
        if (
          !value
          || typeof value.videoId !== "string"
          || !/^[A-Za-z0-9_-]{11}$/.test(value.videoId)
          || typeof value.title !== "string"
          || !value.title.trim()
          || (value.url !== undefined && (typeof value.url !== "string" || !/^https:\/\/(?:www\.)?(?:youtube\.com\/watch\?v=|youtu\.be\/)[A-Za-z0-9_-]{11}(?:[&#?].*)?$/i.test(value.url)))
          || (value.channelName !== undefined && typeof value.channelName !== "string")
        ) {
          fail(`${rel}：metadata.relatedVideo 必须包含有效 videoId/title，可选 url/channelName`);
          continue;
        }
        values.set("relatedVideo", value);
      } catch {
        fail(`${rel}：metadata.relatedVideo 不是有效 JSON 对象`);
      }
      continue;
    }
    const match = line.match(/^([A-Za-z][A-Za-z0-9]*)\s*:\s*("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')\s*,?$/);
    if (!match) {
      fail(`${rel}：metadata 第 ${index + 1} 行必须是单行字符串字面量；只有 relatedVideo 允许单行 JSON 对象`);
      continue;
    }
    const [, field, literal] = match;
    if (!ALLOWED_FIELDS.has(field)) {
      fail(`${rel}：metadata 包含未允许字段 ${field}`);
      continue;
    }
    if (values.has(field)) {
      fail(`${rel}：metadata 字段 ${field} 重复出现`);
      continue;
    }
    try {
      const value = literal.startsWith('"')
        ? JSON.parse(literal)
        : literal.slice(1, -1).replace(/\\(['\\])/g, "$1");
      values.set(field, value);
    } catch {
      fail(`${rel}：metadata 字段 ${field} 不是有效字符串字面量`);
    }
  }
  return values;
}
// ~150KB of MDX prose is already unusually long for a guide article — past this point
// it's more often a duplication/generation bug than a legitimately long article.
const MAX_BYTES = 150_000;

const { env } = resolveIntakeConfig(root);
const articlesDir = path.join(root, env.ARTICLES_DIR);

if (!fs.existsSync(articlesDir)) {
  console.log(`${env.ARTICLES_DIR} 不存在 —— 没有文章可校验（homepage-only 模式）。`);
  process.exit(0);
}

const localeDirs = fs.readdirSync(articlesDir, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name);
let checked = 0;
// "locale/category/slug" -> first file that claimed it — a second file landing on the same
// key would silently overwrite the first one at ingest time (both write to the same
// content/<locale>/<category>/<slug>.mdx), so this has to be caught before that happens.
const seenSlugs = new Map();
const seenTitles = new Map();
const seenDescriptions = new Map();

for (const locale of localeDirs) {
  for (const file of walkMdx(path.join(articlesDir, locale))) {
    checked++;
    const rel = path.relative(root, file);
    const source = fs.readFileSync(file, "utf-8");

    const metadataCount = (source.match(/export const metadata\s*=\s*\{/g) || []).length;
    if (metadataCount === 0) {
      fail(`${rel}：没有找到 export const metadata`);
      continue;
    }
    if (metadataCount > 1) {
      fail(`${rel}：出现了 ${metadataCount} 次 export const metadata，只能有一次（常见于把两篇文章的内容粘到了一个文件里）`);
    }

    const metaMatch = source.match(/^export const metadata\s*=\s*\{([\s\S]*?)^\}/m);
    const metaBody = metaMatch ? metaMatch[1] : "";

    const metadata = parseMetadata(metaBody, rel);
    const missing = REQUIRED_FIELDS.filter((field) => !metadata.get(field)?.trim());
    if (missing.length > 0) fail(`${rel}：metadata 缺少字段（或值为空）：${missing.join(", ")}`);

    const title = metadata.get("title")?.trim() || "";
    const description = metadata.get("description")?.trim() || "";
    for (const [label, value, seen] of [["title", title, seenTitles], ["description", description, seenDescriptions]]) {
      if (!value) continue;
      const key = `${locale}:${value.toLocaleLowerCase(locale)}`;
      if (seen.has(key)) fail(`${rel} 与 ${seen.get(key)} 使用了重复 ${label}`);
      else seen.set(key, rel);
    }
    const cjk = ["ja", "ko", "zh"].includes(locale);
    const titleLimit = cjk ? 36 : 60;
    const descriptionLimit = cjk ? 90 : 160;
    if (title.length > titleLimit) warn(`${rel}：title 有 ${title.length} 个字符，超过 ${locale} 建议上限 ${titleLimit}`);
    if (description.length > descriptionLimit) warn(`${rel}：description 有 ${description.length} 个字符，超过 ${locale} 建议上限 ${descriptionLimit}`);
    if (/(?:&|(?<![\p{L}\p{M}])(?:and|or|with|for|to|vs\.?|und|oder|mit|für|y|o|con|para|et|ou|avec|pour))\s*$/iu.test(title)) {
      fail(`${rel}：title 以未完成的连接词结尾，应在发布前压缩为完整短语`);
    }
    // `\b` is ASCII-oriented in JavaScript. Without a Unicode-aware left
    // boundary, Spanish words such as "Vacío" and "guía" falsely look like
    // dangling `o`/`a`. Keep rejecting real standalone trailing words while
    // never inspecting the final letter of a localized word.
    if (/(?:&|(?<![\p{L}\p{M}])(?:and|or|with|for|to|the|a|an|in|on|at|of|from|into|this|that|your|our))\s*[.!?]?\s*$/iu.test(description)) {
      fail(`${rel}：description 以未完成的虚词结尾，应在发布前压缩为完整句子`);
    }

    const category = metadata.get("category")?.trim();
    if (category) {
      const slug = fileNameToSlug(path.basename(file));
      const key = `${locale}/${category}/${slug}`;
      if (seenSlugs.has(key)) {
        fail(`${rel} 和 ${seenSlugs.get(key)} 接入后会撞到同一个路径 content/${key}.mdx（文件名生成的 slug 相同）—— 两篇会互相覆盖，改其中一个文件名或 category`);
      } else {
        seenSlugs.set(key, rel);
      }
    }

    const bytes = Buffer.byteLength(source, "utf-8");
    if (bytes > MAX_BYTES) {
      warn(`${rel}：文件大小 ${(bytes / 1000).toFixed(0)}KB，明显超出正常攻略文章长度，检查是不是内容重复或生成异常`);
    }

    const callouts = calloutSignature(articleBody(source));
    const body = articleBody(source);
    const placeholder = placeholderMarkdownDestination(body);
    if (placeholder) {
      fail(`${rel}：第 ${placeholder.line} 行 Markdown 链接目标 ${placeholder.destination} 是占位符，必须替换为真实 URL、有效站内路径或具体锚点`);
    }
    if (/^\s*(?:import|export)\b/m.test(body)) {
      fail(`${rel}：正文不允许 import/export；文章只能使用 metadata、Markdown 和受支持的 Callout`);
    }
    if (/(?<!\\)[{}]/.test(body)) {
      fail(`${rel}：正文不允许 MDX JavaScript 表达式花括号；请改为普通 Markdown 文本`);
    }
    if (!balancedCallouts(callouts)) {
      fail(`${rel}：<Callout> 标签未正确闭合`);
    }
    if (/<\/?(?:h[1-6]|ul|ol|li|p)(?:\s+[^>]*)?>/i.test(body)) {
      fail(`${rel}：包含不受支持的原始 HTML 标题/列表标签，应转换为 Markdown`);
    }
  }
}

// Translation is expected to preserve Markdown/MDX structure.  Compare every
// locale with the English source so a provider-truncated response is rejected
// here, before webpack reports a misleading MDX parse error.
const enDir = path.join(articlesDir, "en");
if (fs.existsSync(enDir)) {
  for (const enFile of walkMdx(enDir)) {
    const articleRel = path.relative(enDir, enFile);
    const sourceBody = articleBody(fs.readFileSync(enFile, "utf-8"));
    const sourceHeadings = headingSignature(sourceBody);
    const sourceCallouts = calloutSignature(sourceBody);

    for (const locale of localeDirs.filter((item) => item !== "en")) {
      const translatedFile = path.join(articlesDir, locale, articleRel);
      if (!fs.existsSync(translatedFile)) continue; // check-intake reports tree mismatches
      const translatedBody = articleBody(fs.readFileSync(translatedFile, "utf-8"));
      const rel = path.relative(root, translatedFile);

      if (JSON.stringify(headingSignature(translatedBody)) !== JSON.stringify(sourceHeadings)) {
        fail(`${rel}：标题层级/数量与英文源文不一致，翻译可能被截断`);
      }
      if (JSON.stringify(calloutSignature(translatedBody)) !== JSON.stringify(sourceCallouts)) {
        fail(`${rel}：Callout 结构与英文源文不一致`);
      }
      for (const [label, pattern] of Object.entries(STRUCTURAL_PATTERNS)) {
        const expected = countMatches(sourceBody, pattern);
        const actual = countMatches(translatedBody, pattern);
        if (actual < expected) {
          fail(`${rel}：${label}少于英文源文（${actual}/${expected}），翻译可能不完整`);
        }
      }

      // Keep this aligned with SEO Scout's checkpoint validator. CJK prose can
      // preserve every heading, list, callout and FAQ while using far fewer
      // characters than English; structure parity remains the primary guard.
      const minimumRatio = ["ja", "ko", "zh"].includes(locale) ? 0.40 : 0.80;
      const ratio = translatedBody.length / Math.max(1, sourceBody.length);
      if (ratio < minimumRatio) {
        fail(`${rel}：正文长度仅为英文的 ${ratio.toFixed(2)}，低于 ${minimumRatio.toFixed(2)}`);
      }
      const lastLine = translatedBody.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).at(-1) || "";
      if (lastLine && !/[.!?。！？…|>\])}"'’”]$/.test(lastLine)) {
        fail(`${rel}：正文结尾没有终止标点，翻译可能在句中被截断`);
      }
    }
  }
}

if (errors === 0 && warnings === 0) ok(`${checked} 篇文章全部通过校验（${localeDirs.length} 个语言：${localeDirs.join(", ")}）`);
else console.log(`\n共检查 ${checked} 篇文章。`);

console.log(`\n${errors} error(s), ${warnings} warning(s).`);
process.exit(errors > 0 ? 1 : 0);
