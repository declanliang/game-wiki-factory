import type { Metadata } from "next";
import { getMessages, setRequestLocale } from "next-intl/server";
import { JsonLd } from "@/components/site-widgets";
import { getAllContent, type ContentItem, CONTENT_TYPES } from "@/lib/content";
import { NAVIGATION_CONFIG } from "@/config/navigation";
import { getSiteName, localizedSiteUrl } from "@/config/site";
import { localizeHref } from "@/lib/locale-path";
import { languageAlternates, type Locale } from "@/i18n/routing";
import { buildOpenGraph, buildTwitter, normalizeMetadataDescription, normalizeMetadataTitle } from "@/lib/seo";
import en from "@/locales/en.json";
import HomePageClient from "./HomePageClient";

type Messages = typeof en;

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const messages = (await getMessages({ locale })) as Messages;
  const siteName = getSiteName(messages);
  const title = normalizeMetadataTitle(messages.home.meta.title, locale);
  const description = normalizeMetadataDescription(messages.home.meta.description, locale);
  return {
    title,
    description,
    alternates: { canonical: localizeHref("/", locale), languages: languageAlternates("/") },
    openGraph: buildOpenGraph({ locale, title, description, url: localizedSiteUrl("/", locale), siteName }),
    twitter: buildTwitter({ title, description }),
  };
}

export default async function LocaleHomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const loc = locale as Locale;
  setRequestLocale(locale);
  const messages = (await getMessages({ locale })) as Messages;
  // FAQ answers may contain `[label](href)` links for the on-page accordion; structured
  // data expects plain text, so strip the Markdown syntax down to just the link label.
  const plainTextAnswer = (answer: string) => answer.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
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
  const messagesByKey = messages as unknown as Record<string, { overviewTitle?: string; overviewDescription?: string }>;
  const categories = NAVIGATION_CONFIG
    .filter((item) => item.isContentType && categoryCounts[item.path.replace(/^\//, "")])
    .map((item) => {
      const ct = item.path.replace(/^\//, "");
      const ctMessages = messagesByKey[ct];
      return {
        key: item.key,
        path: item.path,
        title: ctMessages?.overviewTitle || ct.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
        description: ctMessages?.overviewDescription || "",
        count: categoryCounts[ct],
      };
    });

  const officialUrl = messages.site.playUrl;
  const robloxPlace = officialUrl.match(/roblox\.com\/games\/(\d+)/i)?.[1];
  const steamApp = officialUrl.match(/store\.steampowered\.com\/app\/(\d+)/i)?.[1];
  const aboutStats = messages.home.aboutGame.stats;
  const identityFacts = [
    robloxPlace ? { label: "Roblox Place ID", value: robloxPlace } : steamApp ? { label: "Steam App ID", value: steamApp } : null,
    messages.site.developer ? { label: aboutStats[0]?.label || "Developer", value: messages.site.developer } : null,
    messages.site.gamePlatform?.[0] ? { label: aboutStats[1]?.label || "Platform", value: messages.site.gamePlatform[0] } : null,
  ].filter((item): item is { label: string; value: string } => Boolean(item?.value));
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
  const home = {
    ...messages.home,
    featured: {
      ...messages.home.featured,
      items: featuredItems.map((item) => ({
        ...item,
        image: articleImages.get(item.href),
      })),
    },
  };

  return (
    <main className="mx-auto max-w-[90rem] px-5 pb-10 pt-5 sm:px-8 sm:pt-6 lg:px-12">
      {messages.home.faq.items.length > 0 && <JsonLd data={faqPage} />}
      <HomePageClient
        home={home}
        quickFactsLabel={messages.shared.quickFacts}
        videoLabels={messages.shared.homeVideo}
        locale={locale}
        recentArticles={recentArticles}
        categories={categories}
        identityFacts={identityFacts}
        officialUrl={officialUrl}
      />
    </main>
  );
}
