import type { Metadata } from "next";
import { getMessages, setRequestLocale } from "next-intl/server";
import { JsonLd } from "@/components/site-widgets";
import { getAllContent, type ContentItem, CONTENT_TYPES } from "@/lib/content";
import { NAVIGATION_CONFIG } from "@/config/navigation";
import { getSiteName, localizedSiteUrl } from "@/config/site";
import { localizeHref } from "@/lib/locale-path";
import { languageAlternates, type Locale } from "@/i18n/routing";
import { buildOpenGraph, buildTwitter } from "@/lib/seo";
import en from "@/locales/en.json";
import HomePageClient from "./HomePageClient";

type Messages = typeof en;

export async function generateMetadata({
  params,
}: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const messages = (await getMessages({ locale })) as Messages;
  const siteName = getSiteName(messages);
  const title = messages.home.meta.title;
  const description = messages.home.meta.description;
  return {
    title,
    description,
    alternates: {
      canonical: localizeHref("/", locale),
      languages: languageAlternates("/"),
    },
    openGraph: buildOpenGraph({
      locale,
      title,
      description,
      url: localizedSiteUrl("/", locale),
      siteName,
    }),
    twitter: buildTwitter({ title, description }),
  };
}

export default async function LocaleHomePage({
  params,
}: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const loc = locale as Locale;
  setRequestLocale(locale);
  const messages = (await getMessages({ locale })) as Messages;
  // FAQ answers may contain `[label](href)` links for the on-page accordion; structured
  // data expects plain text, so strip the Markdown syntax down to just the link label.
  const plainTextAnswer = (answer: string) =>
    answer.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  const faqPage = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: messages.home.faq.items.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: { "@type": "Answer", text: plainTextAnswer(item.answer) },
    })),
  };

  // 动态加载所有 content 目录下的文章
  const allArticles: ContentItem[] = [];
  const categoryCounts: Record<string, number> = {};
  for (const contentType of CONTENT_TYPES) {
    const items = await getAllContent(contentType, loc);
    allArticles.push(...items);
    if (items.length > 0) categoryCounts[contentType] = items.length;
  }

  // 取最近更新的 4 篇文章（按 date 倒序）——首页只做"最新动态"提示，不是完整列表
  const recentArticles = [...allArticles]
    .sort((a, b) => {
      const dateA = a.metadata.lastModified || a.metadata.date;
      const dateB = b.metadata.lastModified || b.metadata.date;
      return dateB.localeCompare(dateA);
    })
    .slice(0, 4);

  // 分类导航卡片区数据：只保留有文章的分类，标题/描述复用分类列表页已有的
  // overviewTitle/overviewDescription（同一份数据两处使用，不用重复配置）
  const messagesByKey = messages as unknown as Record<
    string,
    { overviewTitle?: string; overviewDescription?: string }
  >;
  const categories = NAVIGATION_CONFIG.filter(
    (item) =>
      item.isContentType && categoryCounts[item.path.replace(/^\//, "")],
  ).map((item) => {
    const ct = item.path.replace(/^\//, "");
    const ctMessages = messagesByKey[ct];
    return {
      key: item.key,
      path: item.path,
      title:
        ctMessages?.overviewTitle ||
        ct.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      description: ctMessages?.overviewDescription || "",
      count: categoryCounts[ct],
    };
  });

  const articleImages = new Map(
    allArticles.map((article) => [
      `/${article.contentType}/${article.slug}`,
      article.metadata.image,
    ]),
  );
  const featuredItems = messages.home.featured.items as Array<{
    title: string;
    description: string;
    href: string;
    category?: string;
  }>;
  type GuideItem = {
    title: string;
    description: string;
    href?: string;
    category?: string;
  };
  type GuideSection = {
    id: string;
    eyebrow: string;
    title: string;
    description: string;
    items: GuideItem[];
  };
  const guideSections = (
    messages.home as unknown as { guideSections?: GuideSection[] }
  ).guideSections;
  const exactArticlePaths = new Set(articleImages.keys());
  const gameTokens = new Set(tokenize(messages.site.name));
  const stopTokens = new Set([
    ...gameTokens,
    "guide",
    "wiki",
    "game",
    "steam",
    "roblox",
    "how",
    "to",
    "the",
    "a",
    "an",
    "and",
    "for",
    "with",
    "overview",
    "guia",
    "juego",
    "como",
    "para",
    "con",
    "und",
    "der",
    "die",
    "das",
    "jeu",
    "avec",
    "pour",
  ]);
  const meaningfulTokens = (value: string) =>
    tokenize(value).filter((token) => !stopTokens.has(token));
  const resolveArticleHref = (item: {
    title: string;
    description?: string;
    href?: string;
  }) => {
    if (item.href && exactArticlePaths.has(item.href)) return item.href;
    const queryTokens = meaningfulTokens(
      `${item.title} ${item.description || ""}`,
    );
    const titleTokens = meaningfulTokens(item.title);
    if (titleTokens.length === 0) return item.href;
    const ranked = allArticles
      .map((article) => {
        const href = `/${article.contentType}/${article.slug}`;
        const candidateTitleTokens = new Set(
          meaningfulTokens(
            `${article.metadata.title} ${article.slug.replace(/-/g, " ")}`,
          ),
        );
        const candidateBodyTokens = new Set(
          meaningfulTokens(article.metadata.description),
        );
        const titleMatches = titleTokens.filter((token) =>
          candidateTitleTokens.has(token),
        ).length;
        const contextMatches = queryTokens.filter((token) =>
          candidateBodyTokens.has(token),
        ).length;
        const completeTitleMatch = titleMatches === titleTokens.length;
        return {
          href,
          score:
            titleMatches * 5 + contextMatches + (completeTitleMatch ? 8 : 0),
          completeTitleMatch,
        };
      })
      .sort((a, b) => b.score - a.score);
    const winner = ranked[0];
    return winner && winner.completeTitleMatch && winner.score >= 13
      ? winner.href
      : item.href;
  };
  const canUseFeaturedMedia = new Set([...articleImages.values()]).size >= 2;
  const usedFeaturedImages = new Set<string>();
  const resolvedFeaturedItems = featuredItems.map((item) => {
    const href = resolveArticleHref(item) || item.href;
    const candidateImage = articleImages.get(href);
    const image =
      canUseFeaturedMedia &&
      candidateImage &&
      !usedFeaturedImages.has(candidateImage)
        ? candidateImage
        : undefined;
    if (image) usedFeaturedImages.add(image);
    return { ...item, href, image };
  });
  const home = {
    ...messages.home,
    featured: {
      ...messages.home.featured,
      items: resolvedFeaturedItems,
    },
    guideSections: guideSections?.map((section) => ({
      ...section,
      items: section.items.map((item) => ({
        ...item,
        href: resolveArticleHref(item),
      })),
    })),
  };

  return (
    <main className="mx-auto max-w-[1240px] px-5 pb-10 pt-5 sm:px-8 sm:pt-6 lg:px-10">
      {messages.home.faq.items.length > 0 && <JsonLd data={faqPage} />}
      <HomePageClient
        home={home}
        quickFactsLabel={messages.shared.quickFacts}
        videoLabels={messages.shared.homeVideo}
        locale={locale}
        recentArticles={recentArticles}
        categories={categories}
      />
    </main>
  );
}

function tokenize(value: string): string[] {
  return value
    .toLocaleLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .split(/[^\p{L}\p{N}]+/u)
    .filter((token) => token.length >= 2);
}
