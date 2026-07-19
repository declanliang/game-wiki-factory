import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronRight, Swords } from "lucide-react";
import { getMessages } from "next-intl/server";
import { Badge } from "@/components/ui/badge";
import { getAllContent, getAllContentPaths, getContent, getDynamicNavigation, type ContentItem } from "@/lib/content";
import { WikiSidebar } from "@/components/site";
import { Breadcrumbs, JsonLd } from "@/components/site-widgets";
import { localizeHref } from "@/lib/locale-path";
import { AdSlot } from "@/components/ad-slot";
import { MobileTOC } from "@/components/table-of-contents";
import { CONTENT_TYPES } from "@/config/navigation";
import { getSiteName, localizedSiteUrl, SITE_LOGO_URL } from "@/config/site";
import { languageAlternates, routing, type Locale } from "@/i18n/routing";
import { buildOpenGraph, buildTwitter } from "@/lib/seo";
import en from "@/locales/en.json";

type Messages = typeof en;

export async function generateStaticParams() {
  const paths = await getAllContentPaths("en");
  const listingPages = CONTENT_TYPES.map((ct) => ({ slug: [ct] }));
  return [...listingPages, ...paths.map((item) => ({ slug: [item.contentType, ...item.slug] }))];
}

export async function generateMetadata({ params }: { params: Promise<{ locale: Locale; slug: string[] }> }): Promise<Metadata> {
  const { locale, slug } = await params;
  const messages = (await getMessages({ locale })) as Messages;
  const siteName = getSiteName(messages);
  if (slug.length === 1 && CONTENT_TYPES.includes(slug[0])) {
    const ct = slug[0];
    const ctTitle = ct.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    const ctMessages = (messages as unknown as Record<string, Record<string, string>>)[ct];
    const title = `${ctMessages?.overviewTitle || ctTitle} — ${siteName}`;
    const description = ctMessages?.overviewDescription || `Browse all ${ctTitle.toLowerCase()} guides and resources for ${messages.site.name}.`;
    const items = await getAllContent(ct, locale);
    return {
      title,
      description,
      // Empty categories (e.g. a generic default like "wiki" a game doesn't use yet) are
      // thin/soft-404 candidates — keep the page reachable but tell crawlers not to index it.
      ...(items.length === 0 ? { robots: { index: false, follow: true } } : {}),
      alternates: { canonical: localizeHref(`/${ct}`, locale), languages: languageAlternates(`/${ct}`) },
      openGraph: buildOpenGraph({ locale, title, description, url: localizedSiteUrl(`/${ct}`, locale), siteName }),
      twitter: buildTwitter({ title, description }),
    };
  }
  const [contentType, ...articleSlug] = slug;
  const item = await getContent(contentType, articleSlug, locale);
  if (!item) return { title: "Not Found" };
  const pathname = `/${contentType}/${articleSlug.join("/")}`;
  const image = item.metadata.image?.startsWith("http") ? item.metadata.image : localizedSiteUrl(item.metadata.image ?? "/images/hero.webp", routing.defaultLocale);
  const title = `${item.metadata.title} — ${siteName}`;
  return {
    title,
    description: item.metadata.description,
    alternates: { canonical: localizeHref(pathname, locale), languages: languageAlternates(pathname) },
    openGraph: buildOpenGraph({ locale, title: item.metadata.title, description: item.metadata.description, url: localizedSiteUrl(pathname, locale), images: [image], type: "article", siteName }),
    twitter: buildTwitter({ title: item.metadata.title, description: item.metadata.description, images: [image] }),
  };
}

export default async function SlugPage({ params }: { params: Promise<{ locale: Locale; slug: string[] }> }) {
  const { locale, slug } = await params;
  const navGroups = getDynamicNavigation(locale);
  if (slug.length === 1) return <NavigationPage locale={locale} contentType={slug[0]} navGroups={navGroups} />;
  return <DetailPage locale={locale} contentType={slug[0]} slug={slug.slice(1)} />;
}

async function NavigationPage({ locale, contentType, navGroups }: { locale: Locale; contentType: string; navGroups: import("@/lib/content").NavGroup[] }) {
  if (!CONTENT_TYPES.includes(contentType)) notFound();
  const messages = (await getMessages({ locale })) as Messages;
  const items = await getAllContent(contentType, locale);
  const listData = { "@context": "https://schema.org", "@type": "ItemList", name: `${contentType} — ${getSiteName(messages)}`, itemListElement: items.map((item, index) => ({ "@type": "ListItem", position: index + 1, url: localizedSiteUrl(`/${contentType}/${item.slug}`, locale), name: item.metadata.title })) };

  // 读取分类标题（优先用 locale JSON 里的，没有就转 slug）
  const sectionTitle = (messages as unknown as Record<string, Record<string, string>>)[contentType]?.overviewTitle
    || contentType.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const sectionDesc = (messages as unknown as Record<string, Record<string, string>>)[contentType]?.overviewDescription || "";
  const breadcrumbData = { "@context": "https://schema.org", "@type": "BreadcrumbList", itemListElement: [{ "@type": "ListItem", position: 1, name: messages.shared.home, item: localizedSiteUrl("/", locale) }, { "@type": "ListItem", position: 2, name: sectionTitle, item: localizedSiteUrl(`/${contentType}`, locale) }] };

  return <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8"><JsonLd data={listData} /><JsonLd data={breadcrumbData} /><div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_300px]"><article><Breadcrumbs items={[{ label: messages.shared.home, href: localizeHref("/", locale) }, { label: sectionTitle }]} /><h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-5xl">{sectionTitle}</h1>{sectionDesc && <p className="mt-5 text-lg leading-8 text-muted-foreground">{sectionDesc}</p>}{items.length > 0 && <><div className="mt-10 grid gap-4 sm:grid-cols-2">{items.map((item) => <Link key={`/${contentType}/${item.slug}`} href={localizeHref(`/${contentType}/${item.slug}`, locale)} className="group rounded-2xl border border-border bg-card/70 p-5 transition hover:-translate-y-0.5 hover:border-[hsl(var(--nav-theme-light))]"><div className="mb-4 flex items-center justify-between gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-muted text-[hsl(var(--nav-theme))]"><Swords className="h-5 w-5" /></span>{item.metadata.badge && <Badge variant="secondary">{item.metadata.badge}</Badge>}</div><h3 className="text-lg font-bold text-foreground group-hover:text-[hsl(var(--nav-theme))]">{item.metadata.title}</h3><p className="mt-2 min-h-[3rem] text-sm leading-6 text-muted-foreground">{item.metadata.description}</p><span className="mt-4 inline-flex items-center text-sm font-semibold text-[hsl(var(--nav-theme))]">{messages.shared.readMore}<ChevronRight className="ml-1 h-4 w-4" /></span></Link>)}</div></>}{items.length === 0 && <p className="mt-8 text-muted-foreground">{messages.shared.noGuidesAvailable}</p>}</article><WikiSidebar locale={locale} navGroups={navGroups} currentPath={`/${contentType}`} /></div></main>;
}

async function DetailPage({ locale, contentType, slug }: { locale: Locale; contentType: string; slug: string[] }) {
  if (!CONTENT_TYPES.includes(contentType)) notFound();
  const messages = (await getMessages({ locale })) as Messages;
  const item = await getContent(contentType, slug, locale);
  if (!item) notFound();
  const pathname = `/${contentType}/${slug.join("/")}`;
  const tocLabel = messages.shared.tableOfContents || messages.shared.inThisSection || "Table of Contents";
  const siteName = getSiteName(messages);
  // 分类措辞跟导航栏、导航页标题用同一个字段（overviewTitle），保证面包屑、Header、列表页标题三处一致。
  const ctMessages = (messages as unknown as Record<string, Record<string, string>>)[contentType];
  const sectionLabel = ctMessages?.overviewTitle || contentType.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const articleUrl = localizedSiteUrl(pathname, locale);
  const articleData = { "@context": "https://schema.org", "@type": "Article", headline: item.metadata.title, description: item.metadata.description, image: item.metadata.image?.startsWith("http") ? item.metadata.image : localizedSiteUrl(item.metadata.image ?? "/images/hero.webp", routing.defaultLocale), datePublished: item.metadata.date, dateModified: item.metadata.lastModified ?? item.metadata.date, mainEntityOfPage: articleUrl, inLanguage: locale, author: { "@type": "Organization", name: siteName }, publisher: { "@type": "Organization", name: siteName, logo: { "@type": "ImageObject", url: SITE_LOGO_URL } } };
  const breadcrumbData = { "@context": "https://schema.org", "@type": "BreadcrumbList", itemListElement: [{ "@type": "ListItem", position: 1, name: messages.shared.home, item: localizedSiteUrl("/", locale) }, { "@type": "ListItem", position: 2, name: sectionLabel, item: localizedSiteUrl(`/${contentType}`, locale) }, { "@type": "ListItem", position: 3, name: item.metadata.title, item: articleUrl }] };
  const faqPageData = item.faqItems.length > 0 ? { "@context": "https://schema.org", "@type": "FAQPage", mainEntity: item.faqItems.map((faq) => ({ "@type": "Question", name: faq.question, acceptedAnswer: { "@type": "Answer", text: faq.answer } })) } : null;

  const relatedLabel = messages.shared.relatedGuides || "Related Guides";
  // Quick Guide 概览框只在文章分段太少、TOC 不会显示时才出现，避免跟下面的 TOC 内容重复。
  const h2Headings = item.headings.filter((h) => h.level === 2);
  const showQuickGuide = item.headings.length > 0 && item.headings.length < 4;

  // Full-width centered column, no persistent right sidebar — the header nav already
  // covers site-wide navigation, so a second WikiSidebar column here was redundant.
  // In-page navigation for long articles is the always-visible MobileTOC below, not a
  // desktop-only sidebar TOC.
  return <main className="mx-auto max-w-4xl px-4 py-10 sm:px-6 lg:px-8"><JsonLd data={articleData} /><JsonLd data={breadcrumbData} />{faqPageData && <JsonLd data={faqPageData} />}<article><Breadcrumbs items={[{ label: messages.shared.home, href: localizeHref("/", locale) }, { label: sectionLabel, href: localizeHref(`/${contentType}`, locale) }, { label: item.metadata.title }]} /><h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-5xl">{item.metadata.title}</h1><p className="mt-5 text-lg leading-8 text-muted-foreground">{item.metadata.summary ?? item.metadata.description}</p><p className="mt-3 text-sm text-muted-foreground">{item.metadata.date}{" · "}{siteName}</p>{showQuickGuide && h2Headings.length >= 2 && <div className="mt-6 rounded-2xl border border-border bg-card/70 p-5"><h3 className="text-xs font-bold uppercase tracking-[0.18em] text-muted-foreground">{messages.shared.quickGuide}</h3><ul className="mt-3 space-y-1.5">{h2Headings.map((h) => <li key={h.id}><a href={`#${h.id}`} className="text-sm text-muted-foreground hover:text-foreground">{h.text}</a></li>)}</ul></div>}<MobileTOC headings={item.headings} label={tocLabel} /><div className="prose prose-lg mt-10 max-w-none"><item.MDXContent /></div><AdSlot format="nativeBanner" className="mt-10" /><ArticleCards locale={locale} contentType={contentType} currentSlug={slug.join("/")} relatedLabel={relatedLabel} sectionLabel={sectionLabel} browseAllLabel={messages.shared.viewAllInCategory} /></article></main>;
}

async function ArticleCards({ locale, contentType, currentSlug, relatedLabel, sectionLabel, browseAllLabel }: { locale: string; contentType: string; currentSlug: string; relatedLabel: string; sectionLabel: string; browseAllLabel: string }) {
  // 动态获取同分类其他文章（排除当前文章），不足 3 篇时跨分类按时间倒序补足，避免模块空白
  const sameCategory = (await getAllContent(contentType, locale as Locale)).filter((item) => item.slug !== currentSlug);
  let related = sameCategory.slice(0, 4);

  if (related.length < 3) {
    const usedSlugs = new Set(related.map((item) => `${item.contentType}/${item.slug}`));
    const otherItems: ContentItem[] = [];
    for (const ct of CONTENT_TYPES) {
      if (ct === contentType) continue;
      otherItems.push(...(await getAllContent(ct, locale as Locale)));
    }
    const fallback = otherItems
      .filter((item) => !usedSlugs.has(`${item.contentType}/${item.slug}`))
      .sort((a, b) => (b.metadata.lastModified || b.metadata.date).localeCompare(a.metadata.lastModified || a.metadata.date))
      .slice(0, 4 - related.length);
    related = [...related, ...fallback];
  }

  if (related.length === 0) return null;

  return <div className="mt-12 space-y-8"><section><h2 className="text-xl font-bold text-foreground">{relatedLabel}</h2><div className="mt-4 grid gap-4 sm:grid-cols-2">{related.map((item) => <SmallCard key={`${item.contentType}/${item.slug}`} icon={<Swords className="h-5 w-5" />} title={item.metadata.title} description={item.metadata.description} href={localizeHref(`/${item.contentType}/${item.slug}`, locale)} />)}</div><Link href={localizeHref(`/${contentType}`, locale)} className="mt-4 inline-flex items-center text-sm font-semibold text-[hsl(var(--nav-theme))] hover:underline">{browseAllLabel.replace("{category}", sectionLabel)}<ChevronRight className="ml-1 h-4 w-4" /></Link></section></div>;
}

function SmallCard({ title, description, href, icon }: { title: string; description: string; href: string; icon?: React.ReactNode }) { return <Link href={href} className="block rounded-2xl border border-border bg-card/70 p-5 transition hover:border-[hsl(var(--nav-theme-light))]">{icon && <div className="mb-3 text-[hsl(var(--nav-theme))]">{icon}</div>}<h4 className="font-bold text-foreground">{title}</h4><p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p></Link>; }
