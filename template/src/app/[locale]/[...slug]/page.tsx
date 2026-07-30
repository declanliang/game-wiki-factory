import type { Metadata } from "next";
import { Fragment } from "react";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronRight, Swords } from "lucide-react";
import { getMessages, setRequestLocale } from "next-intl/server";
import { Badge } from "@/components/ui/badge";
import {
  getAllContent,
  getAllContentPaths,
  getContent,
  getDynamicNavigation,
  type ContentItem,
} from "@/lib/content";
import { WikiSidebar } from "@/components/site";
import { Breadcrumbs, JsonLd } from "@/components/site-widgets";
import { localizeHref } from "@/lib/locale-path";
import {
  ArticleInlineAd,
  DesktopArticleRailAds,
  NativeFlowAd,
} from "@/components/ad-placements";
import { MobileTOC } from "@/components/table-of-contents";
import { CONTENT_TYPES } from "@/config/navigation";
import {
  absoluteAssetUrl,
  getSiteName,
  localizedSiteUrl,
  SITE_LOGO_URL,
} from "@/config/site";
import { languageAlternates, type Locale } from "@/i18n/routing";
import {
  buildCategoryMetadataTitle,
  buildOpenGraph,
  buildTwitter,
} from "@/lib/seo";
import en from "@/locales/en.json";

type Messages = typeof en;

export async function generateStaticParams() {
  const paths = await getAllContentPaths("en");
  const listingPages = CONTENT_TYPES.map((ct) => ({ slug: [ct] }));
  return [
    ...listingPages,
    ...paths.map((item) => ({ slug: [item.contentType, ...item.slug] })),
  ];
}

export async function generateMetadata({
  params,
}: { params: Promise<{ locale: Locale; slug: string[] }> }): Promise<Metadata> {
  const { locale, slug } = await params;
  const messages = (await getMessages({ locale })) as Messages;
  const siteName = getSiteName(messages);
  if (slug.length === 1 && CONTENT_TYPES.includes(slug[0])) {
    const ct = slug[0];
    const ctTitle = ct
      .replace(/-/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
    const ctMessages = (
      messages as unknown as Record<string, Record<string, string>>
    )[ct];
    const categoryTitle = ctMessages?.overviewTitle || ctTitle;
    const categoryDescription =
      ctMessages?.overviewDescription ||
      `Browse all ${ctTitle.toLowerCase()} guides and resources for ${messages.site.name}.`;
    const title = buildCategoryMetadataTitle(
      categoryTitle,
      messages.site.name,
      siteName,
      locale,
    );
    const description = categoryDescription;
    const items = await getAllContent(ct, locale);
    return {
      title,
      description,
      // Empty categories (e.g. a generic default like "wiki" a game doesn't use yet) are
      // thin/soft-404 candidates — keep the page reachable but tell crawlers not to index it.
      ...(items.length === 0 ? { robots: { index: false, follow: true } } : {}),
      alternates: {
        canonical: localizeHref(`/${ct}`, locale),
        languages: languageAlternates(`/${ct}`),
      },
      openGraph: buildOpenGraph({
        locale,
        title,
        description,
        url: localizedSiteUrl(`/${ct}`, locale),
        siteName,
      }),
      twitter: buildTwitter({ title, description }),
    };
  }
  const [contentType, ...articleSlug] = slug;
  const item = await getContent(contentType, articleSlug, locale);
  if (!item) return { title: "Not Found" };
  const pathname = `/${contentType}/${articleSlug.join("/")}`;
  const image = absoluteAssetUrl(item.metadata.image ?? "/images/hero.webp");
  // Article metadata titles already contain the game identity. Appending the
  // site name pushes a large share of SERP titles past the display limit.
  const title = item.metadata.title;
  const description = item.metadata.description;
  return {
    title,
    description,
    alternates: {
      canonical: localizeHref(pathname, locale),
      languages: languageAlternates(pathname),
    },
    openGraph: buildOpenGraph({
      locale,
      title,
      description,
      url: localizedSiteUrl(pathname, locale),
      images: [image],
      type: "article",
      siteName,
    }),
    twitter: buildTwitter({ title, description, images: [image] }),
  };
}

export default async function SlugPage({
  params,
}: { params: Promise<{ locale: Locale; slug: string[] }> }) {
  const { locale, slug } = await params;
  setRequestLocale(locale);
  const navGroups = getDynamicNavigation(locale);
  if (slug.length === 1)
    return (
      <NavigationPage
        locale={locale}
        contentType={slug[0]}
        navGroups={navGroups}
      />
    );
  return (
    <DetailPage locale={locale} contentType={slug[0]} slug={slug.slice(1)} />
  );
}

async function NavigationPage({
  locale,
  contentType,
  navGroups,
}: {
  locale: Locale;
  contentType: string;
  navGroups: import("@/lib/content").NavGroup[];
}) {
  if (!CONTENT_TYPES.includes(contentType)) notFound();
  const messages = (await getMessages({ locale })) as Messages;
  const items = await getAllContent(contentType, locale);
  const listData = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: `${contentType} — ${getSiteName(messages)}`,
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      url: localizedSiteUrl(`/${contentType}/${item.slug}`, locale),
      name: item.metadata.title,
    })),
  };

  // 读取分类标题（优先用 locale JSON 里的，没有就转 slug）
  const sectionTitle =
    (messages as unknown as Record<string, Record<string, string>>)[contentType]
      ?.overviewTitle ||
    contentType.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const sectionDesc =
    (messages as unknown as Record<string, Record<string, string>>)[contentType]
      ?.overviewDescription || "";
  const breadcrumbData = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      {
        "@type": "ListItem",
        position: 1,
        name: messages.shared.home,
        item: localizedSiteUrl("/", locale),
      },
      {
        "@type": "ListItem",
        position: 2,
        name: sectionTitle,
        item: localizedSiteUrl(`/${contentType}`, locale),
      },
    ],
  };
  const canUseCardMedia =
    new Set(items.map((item) => item.metadata.image).filter(Boolean)).size >= 2;
  const seenImages = new Set<string>();
  const cardItems = items.map((item) => {
    const image =
      canUseCardMedia &&
      item.metadata.image &&
      !seenImages.has(item.metadata.image)
        ? item.metadata.image
        : undefined;
    if (image) seenImages.add(image);
    return { ...item, cardImage: image };
  });
  return (
    <main className="mx-auto max-w-[1140px] px-5 py-10 sm:px-8 lg:px-10">
      <JsonLd data={listData} />
      <JsonLd data={breadcrumbData} />
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_280px]">
        <article>
          <Breadcrumbs
            items={[
              { label: messages.shared.home, href: localizeHref("/", locale) },
              { label: sectionTitle },
            ]}
          />
          <h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-5xl">
            {sectionTitle}
          </h1>
          {sectionDesc && (
            <p className="mt-5 max-w-3xl text-lg leading-8 text-muted-foreground">
              {sectionDesc}
            </p>
          )}
          <nav
            aria-label={messages.shared.wikiNavigation}
            className="mt-6 flex gap-2 overflow-x-auto pb-2 lg:hidden"
          >
            {navGroups.map((group) => (
              <Link
                key={group.slug}
                href={localizeHref(`/${group.slug}`, locale)}
                className={`whitespace-nowrap rounded-full border px-3 py-1.5 text-sm font-semibold ${group.slug === contentType ? "border-[hsl(var(--nav-theme))] bg-[hsl(var(--nav-theme)/0.12)] text-[hsl(var(--nav-theme))]" : "border-border text-muted-foreground"}`}
              >
                {group.title}
              </Link>
            ))}
          </nav>
          {cardItems.length > 0 ? (
            <>
              <div className="mt-10 grid gap-4 sm:grid-cols-2">
                {cardItems.map((item, index) => (
                  <Fragment key={`/${contentType}/${item.slug}`}>
                    <Link
                      href={localizeHref(
                        `/${contentType}/${item.slug}`,
                        locale,
                      )}
                      className="group overflow-hidden rounded-2xl border border-border bg-card/70 transition hover:-translate-y-0.5 hover:border-[hsl(var(--nav-theme-light))]"
                    >
                      {item.cardImage ? (
                        <div className="relative aspect-[16/9] bg-muted">
                          <Image
                            src={item.cardImage}
                            alt={item.metadata.imageAlt || ""}
                            fill
                            sizes="(max-width: 640px) 100vw, 420px"
                            className="object-cover transition duration-500 group-hover:scale-[1.03]"
                          />
                        </div>
                      ) : null}
                      <div className="p-5">
                        <div className="mb-4 flex items-center justify-between gap-3">
                          <span className="grid h-10 w-10 place-items-center rounded-xl bg-muted text-[hsl(var(--nav-theme))]">
                            <Swords className="h-5 w-5" />
                          </span>
                          {item.metadata.badge && (
                            <Badge variant="secondary">
                              {item.metadata.badge}
                            </Badge>
                          )}
                        </div>
                        <h2 className="text-lg font-bold text-foreground group-hover:text-[hsl(var(--nav-theme))]">
                          {item.metadata.title}
                        </h2>
                        <p className="mt-2 min-h-[3rem] text-sm leading-6 text-muted-foreground">
                          {item.metadata.description}
                        </p>
                        <span className="mt-4 inline-flex items-center text-sm font-semibold text-[hsl(var(--nav-theme))]">
                          {messages.shared.readMore}
                          <ChevronRight className="ml-1 h-4 w-4" />
                        </span>
                      </div>
                    </Link>
                    {cardItems.length >= 4 && index === 1 ? (
                      <div className="col-span-full py-4">
                        <NativeFlowAd />
                      </div>
                    ) : null}
                  </Fragment>
                ))}
              </div>
            </>
          ) : (
            <p className="mt-8 text-muted-foreground">
              {messages.shared.noGuidesAvailable}
            </p>
          )}
        </article>
        <WikiSidebar
          locale={locale}
          navGroups={navGroups}
          currentPath={`/${contentType}`}
        />
      </div>
    </main>
  );
}

async function DetailPage({
  locale,
  contentType,
  slug,
}: { locale: Locale; contentType: string; slug: string[] }) {
  if (!CONTENT_TYPES.includes(contentType)) notFound();
  const messages = (await getMessages({ locale })) as Messages;
  const item = await getContent(contentType, slug, locale);
  if (!item) notFound();
  const pathname = `/${contentType}/${slug.join("/")}`;
  const tocLabel =
    messages.shared.tableOfContents ||
    messages.shared.inThisSection ||
    "Table of Contents";
  const siteName = getSiteName(messages);
  // 分类措辞跟导航栏、导航页标题用同一个字段（overviewTitle），保证面包屑、Header、列表页标题三处一致。
  const ctMessages = (
    messages as unknown as Record<string, Record<string, string>>
  )[contentType];
  const sectionLabel =
    ctMessages?.overviewTitle ||
    contentType.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const articleUrl = localizedSiteUrl(pathname, locale);
  const articleData = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: item.metadata.title,
    description: item.metadata.description,
    image: absoluteAssetUrl(item.metadata.image ?? "/images/hero.webp"),
    datePublished: item.metadata.date,
    dateModified: item.metadata.lastModified ?? item.metadata.date,
    mainEntityOfPage: articleUrl,
    inLanguage: locale,
    author: { "@type": "Organization", name: siteName },
    publisher: {
      "@type": "Organization",
      name: siteName,
      logo: { "@type": "ImageObject", url: SITE_LOGO_URL },
    },
  };
  const breadcrumbData = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      {
        "@type": "ListItem",
        position: 1,
        name: messages.shared.home,
        item: localizedSiteUrl("/", locale),
      },
      {
        "@type": "ListItem",
        position: 2,
        name: sectionLabel,
        item: localizedSiteUrl(`/${contentType}`, locale),
      },
      {
        "@type": "ListItem",
        position: 3,
        name: item.metadata.title,
        item: articleUrl,
      },
    ],
  };
  const faqPageData =
    item.faqItems.length > 0
      ? {
          "@context": "https://schema.org",
          "@type": "FAQPage",
          mainEntity: item.faqItems.map((faq) => ({
            "@type": "Question",
            name: faq.question,
            acceptedAnswer: { "@type": "Answer", text: faq.answer },
          })),
        }
      : null;

  const relatedLabel = messages.shared.relatedGuides || "Related Guides";
  // Quick Guide 概览框只在文章分段太少、TOC 不会显示时才出现，避免跟下面的 TOC 内容重复。
  const h2Headings = item.headings.filter((h) => h.level === 2);
  const showQuickGuide = item.headings.length > 0 && item.headings.length < 4;

  const articleBodyId = `article-body-${contentType}-${slug.join("-")}`;
  return (
    <main className="mx-auto max-w-[760px] px-5 py-10 sm:px-8">
      <JsonLd data={articleData} />
      <JsonLd data={breadcrumbData} />
      {faqPageData && <JsonLd data={faqPageData} />}
      <DesktopArticleRailAds />
      <article>
        <Breadcrumbs
          items={[
            { label: messages.shared.home, href: localizeHref("/", locale) },
            {
              label: sectionLabel,
              href: localizeHref(`/${contentType}`, locale),
            },
            { label: item.metadata.title },
          ]}
        />
        <h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-5xl">
          {item.metadata.title}
        </h1>
        <p className="mt-5 text-lg leading-8 text-muted-foreground">
          {item.metadata.summary ?? item.metadata.description}
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <Badge variant="secondary">{sectionLabel}</Badge>
          {item.metadata.badge ? (
            <Badge variant="outline">{item.metadata.badge}</Badge>
          ) : null}
          <span>
            {item.metadata.lastModified ?? item.metadata.date}
            {" · "}
            {siteName}
          </span>
        </div>
        {item.metadata.image ? (
          <div className="relative mt-7 aspect-[16/9] overflow-hidden rounded-2xl border border-border bg-muted">
            <Image
              src={item.metadata.image}
              alt={item.metadata.imageAlt || ""}
              fill
              priority
              sizes="(max-width: 896px) 100vw, 896px"
              className="object-cover"
            />
          </div>
        ) : null}
        {showQuickGuide && h2Headings.length >= 2 && (
          <div className="mt-6 rounded-2xl border border-border bg-card/70 p-5">
            <h2 className="text-xs font-bold uppercase tracking-[0.18em] text-muted-foreground">
              {messages.shared.quickGuide}
            </h2>
            <ul className="mt-3 space-y-1.5">
              {h2Headings.map((h) => (
                <li key={h.id}>
                  <a
                    href={`#${h.id}`}
                    className="text-sm text-muted-foreground hover:text-foreground"
                  >
                    {h.text}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
        <MobileTOC headings={item.headings} label={tocLabel} />
        <div id={articleBodyId} className="prose prose-lg mt-10 max-w-none">
          <item.MDXContent />
        </div>
        <ArticleInlineAd containerId={articleBodyId} />
        <ArticleCards
          locale={locale}
          contentType={contentType}
          currentSlug={slug.join("/")}
          relatedLabel={relatedLabel}
          sectionLabel={sectionLabel}
          browseAllLabel={messages.shared.viewAllInCategory}
        />
      </article>
    </main>
  );
}

async function ArticleCards({
  locale,
  contentType,
  currentSlug,
  relatedLabel,
  sectionLabel,
  browseAllLabel,
}: {
  locale: string;
  contentType: string;
  currentSlug: string;
  relatedLabel: string;
  sectionLabel: string;
  browseAllLabel: string;
}) {
  // Related content must share the same user intent/category. A short relevant
  // list is better than filling the module with unrelated pages.
  const sameCategory = (
    await getAllContent(contentType, locale as Locale)
  ).filter((item) => item.slug !== currentSlug);
  const related = sameCategory.slice(0, 4);

  if (related.length === 0) return null;

  const canUseRelatedMedia =
    new Set(related.map((item) => item.metadata.image).filter(Boolean)).size >=
    2;
  const seenImages = new Set<string>();
  return (
    <div className="mt-12 space-y-8">
      <section>
        <h2 className="text-xl font-bold text-foreground">{relatedLabel}</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {related.map((item) => {
            const image =
              canUseRelatedMedia &&
              item.metadata.image &&
              !seenImages.has(item.metadata.image)
                ? item.metadata.image
                : undefined;
            if (image) seenImages.add(image);
            return (
              <SmallCard
                key={`${item.contentType}/${item.slug}`}
                icon={<Swords className="h-5 w-5" />}
                title={item.metadata.title}
                description={item.metadata.description}
                image={image}
                imageAlt={item.metadata.imageAlt}
                href={localizeHref(`/${item.contentType}/${item.slug}`, locale)}
              />
            );
          })}
        </div>
        <Link
          href={localizeHref(`/${contentType}`, locale)}
          className="mt-4 inline-flex items-center text-sm font-semibold text-[hsl(var(--nav-theme))] hover:underline"
        >
          {browseAllLabel.replace("{category}", sectionLabel)}
          <ChevronRight className="ml-1 h-4 w-4" />
        </Link>
      </section>
    </div>
  );
}

function SmallCard({
  title,
  description,
  href,
  icon,
  image,
  imageAlt,
}: {
  title: string;
  description: string;
  href: string;
  icon?: React.ReactNode;
  image?: string;
  imageAlt?: string;
}) {
  return (
    <Link
      href={href}
      className="block overflow-hidden rounded-2xl border border-border bg-card/70 transition hover:border-[hsl(var(--nav-theme-light))]"
    >
      {image ? (
        <div className="relative aspect-[16/9] bg-muted">
          <Image
            src={image}
            alt={imageAlt || ""}
            fill
            sizes="(max-width: 640px) 100vw, 420px"
            className="object-cover"
          />
        </div>
      ) : null}
      <div className="p-5">
        {icon && (
          <div className="mb-3 text-[hsl(var(--nav-theme))]">{icon}</div>
        )}
        <h3 className="font-bold text-foreground">{title}</h3>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {description}
        </p>
      </div>
    </Link>
  );
}
