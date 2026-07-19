import fs from "fs";
import path from "path";
import { CONTENT_TYPES as CONFIG_CONTENT_TYPES, SITE_PLAN_CATEGORIES } from "@/config/navigation";
import { routing, type Locale } from "@/i18n/routing";

// 从统一配置导入内容类型
export const CONTENT_TYPES = CONFIG_CONTENT_TYPES;

/**
 * 将文件名转换为 URL-safe slug
 * 所有非字母数字连字符下划线的字符（冒号、问号、井号、空格等）替换为 -
 * 合并连续的 -，去掉首尾 -
 */
export function fileNameToSlug(fileName: string): string {
  return fileName
    .replace(/\.mdx$/, "")
    .replace(/[^a-zA-Z0-9\-_]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

/**
 * 根据 slug 在目录中反查真实文件名（不含 .mdx）
 * 例如 slug="gelum-boss" → 返回 "gelum:boss"
 */
export function findFileBySlug(dir: string, slug: string, basePath: string[] = []): string | null {
  if (!fs.existsSync(dir)) return null;
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      const result = findFileBySlug(fullPath, slug, [...basePath, entry.name]);
      if (result) return result;
    } else if (entry.name.endsWith(".mdx")) {
      const fileName = entry.name.replace(".mdx", "");
      const entrySlug = [...basePath, fileNameToSlug(fileName)].join("/");
      if (entrySlug === slug) {
        return [...basePath, fileName].join("/");
      }
    }
  }
  return null;
}

// 通用 Metadata 接口（与 MDX 文件 export const metadata 对应）
export interface ContentMetadata {
  title: string;
  description: string;
  category: string;
  date: string;
  lastModified?: string;
  image?: string;
  badge?: string;
  summary?: string;
}

// Heading 结构（从 MDX 源文件提取）
export interface Heading {
  id: string;
  text: string;
  level: number;
}

// FAQ 问答对（从 MDX 源文件尾部的 FAQ 段落解析，用于生成 FAQPage 结构化数据）
export interface FaqItem {
  question: string;
  answer: string;
}

// 内容项接口
export interface ContentItem {
  slug: string;
  segments: string[];
  contentType: string;
  locale: Locale;
  metadata: ContentMetadata;
}

// 内容数据接口（含 MDX 组件）
export type ContentData = {
  slug: string;
  segments: string[];
  contentType: string;
  locale: Locale;
  metadata: ContentMetadata;
  MDXContent: React.ComponentType;
  headings: Heading[];
  faqItems: FaqItem[];
};

const CONTENT_ROOT = path.join(process.cwd(), "content");

/**
 * 从 MDX 源文件中提取 ## 和 ### 标题
 */
function extractHeadings(mdxSource: string): Heading[] {
  const headings: Heading[] = [];
  const lines = mdxSource.split("\n");
  for (const line of lines) {
    const match = line.match(/^(#{2,3})\s+(.+)/);
    if (match) {
      const level = match[1].length;
      const text = match[2].replace(/\{[^}]*\}/g, "").trim();
      const id = text
        .toLowerCase()
        .replace(/[^a-z0-9\s-]/g, "")
        .replace(/\s+/g, "-")
        .replace(/-+/g, "-")
        .replace(/^-|-$/g, "");
      headings.push({ id, text, level });
    }
  }
  return headings;
}

/**
 * 读取 MDX 源文件并提取 headings
 */
function getHeadingsFromFile(filePath: string): Heading[] {
  try {
    const source = fs.readFileSync(filePath, "utf-8");
    return extractHeadings(source);
  } catch {
    return [];
  }
}

/**
 * 从 MDX 源文件尾部的 FAQ 段落解析问答对（用于 FAQPage 结构化数据）。
 * 内容来源是自由格式 Markdown 文本，不是强 schema——按行扫描，遇到"问句标记行"
 * （`### 问题` 或独占一行的 `**问题**`）就开一个新条目，之后的行（不管有没有空行
 * 隔开）都并入当前答案，直到遇到下一个问句标记行为止。这样能兼容问句和答案之间
 * 有没有空行的各种写法，不需要预判具体格式。解析不出至少 2 条就返回空数组，
 * 调用方据此静默跳过 FAQPage schema，不影响正文照常渲染。
 */
function extractFaqItems(mdxSource: string): FaqItem[] {
  const lines = mdxSource.split("\n");

  let faqStart = -1;
  for (let i = 0; i < lines.length; i++) {
    if (/^##\s+/.test(lines[i]) && /faq|frequently asked questions/i.test(lines[i])) faqStart = i;
  }
  if (faqStart === -1) return [];

  let faqEnd = lines.length;
  for (let i = faqStart + 1; i < lines.length; i++) {
    if (/^##\s+/.test(lines[i])) { faqEnd = i; break; }
  }

  type Draft = { question: string; answerLines: string[] };
  const drafts: Draft[] = [];
  let current: Draft | null = null;

  for (const rawLine of lines.slice(faqStart + 1, faqEnd)) {
    const line = rawLine.trim();
    if (!line) continue;
    const headingMatch = line.match(/^###\s+(.+)/);
    const boldMatch = line.match(/^\*\*(?:Q:\s*)?(.+?)\*\*\s*$/);
    const question = (headingMatch?.[1] ?? boldMatch?.[1])?.trim();
    if (question) {
      if (current) drafts.push(current);
      current = { question, answerLines: [] };
    } else if (current) {
      current.answerLines.push(line);
    }
  }
  if (current) drafts.push(current);

  const items: FaqItem[] = drafts
    .map(({ question, answerLines }) => ({
      question,
      answer: answerLines.join(" ").replace(/^A:\s*/i, "").replace(/\*\*/g, "").replace(/\s+/g, " ").trim(),
    }))
    .filter((item) => item.question && item.answer);

  return items.length >= 2 ? items.slice(0, 10) : [];
}

/**
 * 读取 MDX 源文件并提取 FAQ 问答对
 */
function getFaqItemsFromFile(filePath: string): FaqItem[] {
  try {
    const source = fs.readFileSync(filePath, "utf-8");
    return extractFaqItems(source);
  } catch {
    return [];
  }
}

/**
 * 辅助函数：递归获取目录下所有 MDX 文件的 slug 路径
 */
function getSlugsFromDirectory(dir: string, basePath: string[] = []): string[][] {
  if (!fs.existsSync(dir)) return [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const paths: string[][] = [];

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      paths.push(...getSlugsFromDirectory(fullPath, [...basePath, entry.name]));
    } else if (entry.name.endsWith(".mdx")) {
      const fileName = entry.name.replace(".mdx", "");
      paths.push([...basePath, fileNameToSlug(fileName)]);
    }
  }
  return paths;
}

/**
 * 获取所有内容列表（支持递归读取嵌套目录）
 * 使用动态 import 获取 MDX 文件的 metadata
 */
export async function getAllContent(contentType: string, language: Locale): Promise<ContentItem[]> {
  const contentDir = path.join(CONTENT_ROOT, language, contentType);
  const slugPaths = getSlugsFromDirectory(contentDir);

  const items = await Promise.all(
    slugPaths.map(async (segments) => {
      const slug = segments.join("/");
      try {
        const realSlug = findFileBySlug(contentDir, slug) || slug;
        const mod = await import(`../../content/${language}/${contentType}/${realSlug}.mdx`);
        return {
          slug,
          segments,
          contentType,
          locale: language,
          metadata: mod.metadata as ContentMetadata,
        } satisfies ContentItem;
      } catch {
        return null;
      }
    }),
  );

  return items
    .filter((item): item is ContentItem => Boolean(item))
    .sort((a, b) => a.metadata.title.localeCompare(b.metadata.title));
}

/**
 * 获取单个内容项（含 MDX 渲染后的内容组件）
 * 使用动态 import 直接导入 .mdx 文件
 */
export async function getContent(contentType: string, slugSegments: string[], language: Locale): Promise<ContentData | null> {
  const currentSlug = slugSegments.join("/");
  const contentDir = path.join(CONTENT_ROOT, language, contentType);

  try {
    const realSlug = findFileBySlug(contentDir, currentSlug) || currentSlug;
    const mdxPath = path.join(contentDir, `${realSlug}.mdx`);
    const { default: MDXContent, metadata } = await import(
      `../../content/${language}/${contentType}/${realSlug}.mdx`
    );

    return {
      slug: currentSlug,
      segments: slugSegments,
      contentType,
      locale: language,
      metadata: metadata as ContentMetadata,
      MDXContent,
      headings: getHeadingsFromFile(mdxPath),
      faqItems: getFaqItemsFromFile(mdxPath),
    };
  } catch {
    // Locale completeness is validated before build. Never serve English body
    // content under a non-English URL if a file is missing or invalid.
    return null;
  }
}

/**
 * 导航分组结构（用于动态 Wiki Navigation）
 */
export interface NavGroup {
  /** 分组标题，来自目录名转人类可读格式，如 "bosses" → "Bosses" */
  title: string;
  /** 该分组下的文章数量 */
  count: number;
  /** 分组 slug（即目录名，如 "bosses"） */
  slug: string;
  /** 文章链接列表 */
  links: Array<{ label: string; href: string; badge?: string }>;
}

// 各语言的分组标题映射，key 为 locale，值同上（slug → 该语言标题）
const GROUP_TITLES_BY_LOCALE: Record<string, Record<string, string>> = Object.fromEntries(
  routing.locales.map((locale) => [
    locale,
    Object.fromEntries(
      SITE_PLAN_CATEGORIES.map((category) => [category.id, category.labels[locale]]),
    ),
  ]),
);

// locale → "Overview" translation; every fixed locale is required.
const OVERVIEW_LABEL_BY_LOCALE: Record<string, string> = {
  en: "Overview", es: "Resumen", de: "Übersicht", fr: "Aperçu", ja: "概要", ko: "개요",
};

// 分组排序顺序，未列出的分组按发现顺序排在最后
const GROUP_ORDER: string[] = SITE_PLAN_CATEGORIES.map((category) => category.id);

/**
 * 动态生成 Wiki Navigation 分组
 * 扫描 content/<locale>/ 下的所有 MDX 文件，按子目录分组
 * 同时为列表页添加 Overview 入口
 */
export function getDynamicNavigation(language: Locale = "en"): NavGroup[] {
  const localeDir = path.join(CONTENT_ROOT, language);
  if (!fs.existsSync(localeDir)) return [];

  const entries = fs.readdirSync(localeDir, { withFileTypes: true });
  const groups: NavGroup[] = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const groupSlug = entry.name;
    // 跳过不在 CONTENT_TYPES 中的目录，避免显示会 404 的导航链接
    if (!CONTENT_TYPES.includes(groupSlug as typeof CONTENT_TYPES[number])) continue;
    const groupDir = path.join(localeDir, groupSlug);
    const slugPaths = getSlugsFromDirectory(groupDir);

    if (slugPaths.length === 0) continue;

    const links: NavGroup["links"] = [];
    // 添加 Overview 入口（按 locale 翻译）
    const overviewLabel = OVERVIEW_LABEL_BY_LOCALE[language];
    links.push({ label: overviewLabel, href: `/${groupSlug}` });

    for (const segments of slugPaths) {
      const articleSlug = segments.join("/");
      const mdxFilePath = findFileBySlug(groupDir, articleSlug);
      if (!mdxFilePath) continue;

      const fullPath = path.join(groupDir, `${mdxFilePath}.mdx`);
      let title = segments[segments.length - 1].replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
      let badge: string | undefined;

      try {
        const source = fs.readFileSync(fullPath, "utf-8");
        // 提取 metadata.title
        const titleMatch = source.match(/title:\s*["'](.+?)["']/);
        if (titleMatch) title = titleMatch[1];
        // 提取 metadata.badge
        const badgeMatch = source.match(/badge:\s*["'](.+?)["']/);
        if (badgeMatch) badge = badgeMatch[1];
      } catch {
        // 读取失败用默认标题
      }

      links.push({ label: title, href: `/${groupSlug}/${articleSlug}`, badge });
    }

    // Site-plan validation guarantees a locale-specific title.
    const localTitles = GROUP_TITLES_BY_LOCALE[language];
    const groupTitle = localTitles[groupSlug];

    groups.push({
      title: groupTitle,
      count: links.length - 1, // 减去 Overview
      slug: groupSlug,
      links,
    });
  }

  // 按 GROUP_ORDER 排序
  groups.sort((a, b) => {
    const ai = GROUP_ORDER.indexOf(a.slug);
    const bi = GROUP_ORDER.indexOf(b.slug);
    return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
  });

  return groups;
}

/**
 * 获取所有内容路径（用于 generateStaticParams）
 */
export async function getAllContentPaths(language: Locale) {
  const localeDir = path.join(CONTENT_ROOT, language);
  if (!fs.existsSync(localeDir)) return [];

  const entries = fs.readdirSync(localeDir, { withFileTypes: true });
  const contentTypeDirs = entries.filter((entry) => entry.isDirectory());

  const paths = contentTypeDirs.flatMap((entry) => {
    const segments = getSlugsFromDirectory(path.join(localeDir, entry.name));
    return segments.map((slug) => ({ contentType: entry.name, slug }));
  });

  return paths;
}
