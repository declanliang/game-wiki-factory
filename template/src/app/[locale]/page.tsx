import type { Metadata } from "next";
import { getMessages } from "next-intl/server";
import { JsonLd } from "@/components/site-widgets";
import { getAllContent, type ContentItem, CONTENT_TYPES } from "@/lib/content";
import { NAVIGATION_CONFIG } from "@/config/navigation";
import { getSiteName, SITE_URL } from "@/config/site";
import { languageAlternates, routing, type Locale } from "@/i18n/routing";
import { buildOpenGraph, buildTwitter } from "@/lib/seo";
import en from "@/locales/en.json";
import HomePageClient from "./HomePageClient";

const siteUrl = SITE_URL;

type Messages = typeof en;

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const messages = (await getMessages({ locale })) as Messages;
  const siteName = getSiteName(messages);
  const { title, description } = messages.home.meta;
  return {
    title,
    description,
    alternates: { canonical: locale === routing.defaultLocale ? "/" : `/${locale}`, languages: languageAlternates("/") },
    openGraph: buildOpenGraph({ locale, title, description, url: siteUrl, siteName }),
    twitter: buildTwitter({ title, description }),
  };
}

export default async function LocaleHomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const loc = locale as Locale;
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

  return (
    <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      {messages.home.faq.items.length > 0 && <JsonLd data={faqPage} />}
      <HomePageClient home={messages.home} quickFactsLabel={messages.shared.quickFacts} locale={locale} recentArticles={recentArticles} categories={categories} />
    </main>
  );
}
