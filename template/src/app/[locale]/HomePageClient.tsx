"use client";

import { Fragment } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  ArrowRight,
  BookOpen,
  ChevronRight,
  type LucideIcon,
} from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TrailerButton } from "@/components/trailer";
import { localizeHref } from "@/lib/locale-path";
import { useAdEnabled } from "@/components/ad-slot";
import {
  DesktopBanner728,
  NativeFlowAd,
  ResponsiveContentAd,
} from "@/components/ad-placements";
import { NAVIGATION_CONFIG } from "@/config/navigation";
import { HOME_SECTION_ORDER, type HomeSection } from "@/config/home";
import type { ContentItem } from "@/lib/content";
import en from "@/locales/en.json";

// Lightweight "icon + title + one-line description + link" card item — used by the
// Featured Guides block. `category` is optional and, when
// it matches a registered NAVIGATION_CONFIG key, borrows that category's icon so games
// don't need a separate icon vocabulary just for these cards.
type LightItem = {
  title: string;
  description: string;
  href: string;
  category?: string;
  image?: string;
};
// `description` is an optional keyword-bearing intro line under the heading.
type LightSection = {
  title: string;
  description?: string;
  viewAllHref?: string;
  viewAllLabel?: string;
  items: LightItem[];
};
type GuideItem = {
  title: string;
  description: string;
  category?: string;
  href?: string;
};
type GuideSection = {
  id: string;
  eyebrow: string;
  title: string;
  description: string;
  items: GuideItem[];
};
type VideoLabels = {
  eyebrow: string;
  title: string;
  description: string;
  play: string;
  watchOnYouTube: string;
};
type Home = Omit<
  typeof en.home,
  "featured" | "liveTools" | "hero" | "guideSections"
> & {
  hero: Omit<typeof en.home.hero, "videoId"> & { videoId?: string };
  featured: LightSection;
  liveTools?: LightSection;
  // Zero or more additional category-highlight blocks — the homepage's one open-ended
  // extension point, see the HOME_SECTIONS comment in src/config/home.ts.
  extraSections?: LightSection[];
  guideSections?: GuideSection[];
};

type Category = {
  key: string;
  path: string;
  title: string;
  description: string;
  count: number;
};
const iconByKey: Record<string, LucideIcon> = Object.fromEntries(
  NAVIGATION_CONFIG.map((item) => [item.key, item.icon]),
);

// Renders a FAQ answer that may contain `[label](href)` links — the only Markdown syntax
// supported here, kept intentionally minimal so answers stay easy to author without pulling
// in a full Markdown renderer just for this one field.
function renderFaqAnswer(text: string, locale: string) {
  const parts = text.split(/(\[[^\]]+\]\([^)]+\))/g);
  return parts.map((part, i) => {
    const match = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (!match) return <span key={i}>{part}</span>;
    const [, label, href] = match;
    const isExternal = /^([a-z][a-z0-9+.-]*:)?\/\//i.test(href);
    return (
      <Link
        key={i}
        href={isExternal ? href : localizeHref(href, locale)}
        className="font-semibold text-[hsl(var(--nav-theme))] hover:underline"
      >
        {label}
      </Link>
    );
  });
}

// Renders `**text**` as a highlighted keyword — used for the About-game paragraphs so
// authors can call out the game name, developer, setting, etc. without a full Markdown renderer.
function renderBoldText(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    const match = part.match(/^\*\*([^*]+)\*\*$/);
    if (!match) return <span key={i}>{part}</span>;
    return (
      <strong key={i} className="font-semibold text-[hsl(var(--nav-theme))]">
        {match[1]}
      </strong>
    );
  });
}

function LightCard({ item, locale }: { item: LightItem; locale: string }) {
  const Icon = (item.category && iconByKey[item.category]) || BookOpen;
  return (
    <Link
      href={localizeHref(item.href, locale)}
      className="group flex w-full max-w-[22rem] flex-col overflow-hidden rounded-2xl border border-border bg-card/70 transition hover:-translate-y-0.5 hover:border-[hsl(var(--nav-theme-light))]"
    >
      {item.image ? (
        <span className="relative block aspect-[16/9] overflow-hidden bg-muted">
          <Image
            src={item.image}
            alt=""
            fill
            sizes="(max-width: 640px) 100vw, 352px"
            className="object-cover transition duration-500 group-hover:scale-[1.03]"
          />
          <span className="absolute inset-0 bg-gradient-to-t from-black/45 to-transparent" />
        </span>
      ) : null}
      <span className="flex items-start gap-3 p-4">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-muted text-[hsl(var(--nav-theme))]">
          <Icon className="h-4 w-4" />
        </span>
        <span className="min-w-0">
          <span className="block text-lg font-semibold text-foreground group-hover:text-[hsl(var(--nav-theme))]">
            {item.title}
          </span>
          <span className="mt-1 block text-base leading-6 text-muted-foreground line-clamp-2">
            {item.description}
          </span>
        </span>
      </span>
    </Link>
  );
}

function LightSectionBlock({
  section,
  locale,
  insertAd = false,
  taskRouter = false,
}: {
  section: LightSection;
  locale: string;
  insertAd?: boolean;
  taskRouter?: boolean;
}) {
  if (!section.items || section.items.length === 0) return null;
  return (
    <section
      className={`mx-auto ${taskRouter ? "max-w-[1000px] rounded-[2rem] border border-border bg-card/40 px-5 py-8 sm:px-8 sm:py-10" : "max-w-[920px]"}`}
    >
      {taskRouter ? (
        <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-[hsl(var(--nav-theme)/0.12)] text-[hsl(var(--nav-theme))]">
          <ArrowRight className="h-5 w-5" />
        </div>
      ) : null}
      <h2 className="text-center text-3xl font-bold tracking-tight text-foreground sm:text-5xl">
        {section.title}
      </h2>
      {section.description && (
        <p className="mx-auto mt-4 max-w-3xl text-center text-lg text-muted-foreground">
          {section.description}
        </p>
      )}
      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {(taskRouter ? section.items.slice(0, 6) : section.items).map(
          (item, index) => (
            <Fragment key={item.href}>
              <LightCard item={item} locale={locale} />
              {insertAd && index === 2 && section.items.length > 3 ? (
                <div className="py-4 sm:col-span-2 lg:col-span-3">
                  <ResponsiveContentAd />
                </div>
              ) : null}
            </Fragment>
          ),
        )}
      </div>
      {section.viewAllHref && (
        <div className="mt-6 text-center">
          <Link
            href={localizeHref(section.viewAllHref, locale)}
            className="inline-flex items-center text-base font-semibold text-[hsl(var(--nav-theme))] hover:underline"
          >
            {section.viewAllLabel || "View All"}{" "}
            <ChevronRight className="ml-1 h-4 w-4" />
          </Link>
        </div>
      )}
    </section>
  );
}

function GuideSectionsBlock({
  sections,
  locale,
}: { sections: GuideSection[]; locale: string }) {
  return (
    <section
      aria-label="Game field guide"
      className="mx-auto max-w-[1040px] space-y-14 sm:space-y-16"
    >
      {sections.map((section) => {
        const SectionIcon =
          iconByKey[section.id] ||
          iconByKey[
            section.items.find((item) => item.category)?.category || ""
          ] ||
          BookOpen;
        return (
          <article
            key={section.id}
            className="grid gap-7 lg:grid-cols-[0.7fr_1.3fr] lg:gap-12"
          >
            <div className="lg:self-start">
              <div className="flex items-center gap-3 text-xs font-bold uppercase tracking-[0.24em] text-[hsl(var(--nav-theme))]">
                <span className="grid h-12 w-12 place-items-center rounded-2xl border border-[hsl(var(--nav-theme)/0.35)] bg-[hsl(var(--nav-theme)/0.1)] text-[hsl(var(--nav-theme))]">
                  <SectionIcon className="h-6 w-6" />
                </span>
                <span>{section.eyebrow}</span>
              </div>
              <h2 className="mt-4 text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
                {section.title}
              </h2>
              <p className="mt-4 max-w-xl text-base leading-7 text-muted-foreground">
                {section.description}
              </p>
            </div>
            <ul className="grid gap-4">
              {section.items.map((item, itemIndex) => {
                const ItemIcon =
                  (item.category && iconByKey[item.category]) || SectionIcon;
                const body = (
                  <div className="grid grid-cols-[3.75rem_1fr_auto] gap-5 rounded-2xl border border-border bg-card/70 p-5 transition group-hover:-translate-y-0.5 group-hover:border-[hsl(var(--nav-theme-light))]">
                    <span className="grid h-14 w-14 place-items-center rounded-2xl bg-muted text-[hsl(var(--nav-theme))]">
                      <ItemIcon className="h-7 w-7" />
                    </span>
                    <span>
                      <span className="block text-lg font-semibold text-foreground group-hover:text-[hsl(var(--nav-theme))]">
                        {item.title}
                      </span>
                      <span className="mt-1 block text-sm leading-6 text-muted-foreground">
                        {item.description}
                      </span>
                    </span>
                    {item.href ? (
                      <ArrowRight className="mt-1 h-4 w-4 text-muted-foreground transition group-hover:translate-x-1 group-hover:text-[hsl(var(--nav-theme))]" />
                    ) : null}
                  </div>
                );
                return item.href ? (
                  <li key={`${section.id}-${itemIndex}`}>
                    <Link
                      className="group block"
                      href={localizeHref(item.href, locale)}
                    >
                      {body}
                    </Link>
                  </li>
                ) : (
                  <li key={`${section.id}-${itemIndex}`}>{body}</li>
                );
              })}
            </ul>
          </article>
        );
      })}
    </section>
  );
}

export default function HomePageClient({
  home,
  quickFactsLabel,
  videoLabels,
  locale,
  recentArticles,
  categories,
}: {
  home: Home;
  quickFactsLabel: string;
  videoLabels: VideoLabels;
  locale: string;
  recentArticles: ContentItem[];
  categories: Category[];
}) {
  const nativeEnabled = useAdEnabled("nativeBanner");
  const nativeMobileEnabled = useAdEnabled("nativeBannerMobile");
  const anyNativeEnabled = nativeEnabled || nativeMobileEnabled;
  const banner728Enabled = useAdEnabled("banner728x90");
  const banner300Enabled = useAdEnabled("banner300x250");
  function renderSection(section: HomeSection) {
    switch (section) {
      case "hero":
        return (
          <section className="relative mx-auto min-h-[32rem] max-w-[1160px] overflow-hidden rounded-[2rem] border border-white/10 bg-card text-center shadow-2xl shadow-black/30">
            <Image
              src="/images/hero.webp"
              alt=""
              fill
              priority
              sizes="(max-width: 1440px) 100vw, 1440px"
              className="object-cover"
            />
            <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(4,6,10,.38)_0%,rgba(4,6,10,.62)_48%,rgba(4,6,10,.94)_100%)]" />
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_28%,transparent_0%,rgba(0,0,0,.2)_52%,rgba(0,0,0,.6)_100%)]" />
            <div className="relative z-10 mx-auto flex min-h-[32rem] max-w-[1040px] flex-col px-5 pb-6 pt-6 sm:px-10 lg:px-14">
              <div className="flex flex-1 flex-col items-center justify-center py-4 sm:py-5">
                <div className="mx-auto mb-4 flex justify-center">
                  <span className="inline-flex items-center rounded-full border border-white/25 bg-black/35 px-4 py-1.5 text-sm font-semibold text-white backdrop-blur-md">
                    {home.hero.eyebrow}
                  </span>
                </div>
                <h1 className="text-5xl font-extrabold tracking-[-0.045em] text-white drop-shadow-2xl sm:text-6xl lg:text-7xl">
                  {home.hero.title}
                </h1>
                <p className="mx-auto mt-5 max-w-3xl text-lg leading-relaxed text-white/80 drop-shadow-lg sm:text-xl">
                  {home.hero.description}
                </p>
                <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
                  <Button
                    asChild
                    size="lg"
                    className="shadow-lg shadow-black/20"
                  >
                    <Link href={localizeHref(home.hero.primaryCtaHref, locale)}>
                      {home.hero.primaryCta}
                    </Link>
                  </Button>
                  <Button
                    asChild
                    size="lg"
                    variant="outline"
                    className="border-white/35 bg-black/25 text-white backdrop-blur-md hover:bg-white hover:text-black"
                  >
                    <Link href={home.hero.secondaryCtaHref}>
                      {home.hero.secondaryCta}
                    </Link>
                  </Button>
                </div>
              </div>
              <div className="mx-auto grid w-full max-w-4xl grid-cols-2 gap-3 sm:grid-cols-4">
                {home.hero.stats.map((stat) => (
                  <div
                    key={stat.label}
                    className="flex min-h-28 flex-col rounded-2xl border border-white/15 bg-black/40 p-5 text-left text-white shadow-lg backdrop-blur-md sm:min-h-32 sm:p-5"
                  >
                    <p className="text-2xl font-bold leading-tight text-white sm:text-3xl">
                      {stat.value}
                    </p>
                    <p className="mt-auto pt-5 text-sm leading-5 text-white/65">
                      {stat.label}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </section>
        );

      case "ads":
        return anyNativeEnabled ? <NativeFlowAd /> : null;

      case "bottomAd":
        return banner728Enabled ? <DesktopBanner728 /> : null;

      case "about":
        return (
          // Centered heading + divider, then paragraphs (left) / Quick Facts box (right)
          <section className="mx-auto max-w-[1040px]">
            <div className="text-center">
              <h2 className="text-3xl font-bold tracking-tight text-foreground sm:text-5xl">
                {home.aboutGame.title}
              </h2>
              <div className="mx-auto mt-4 h-px w-24 bg-border" />
            </div>
            <div className="mt-10 grid gap-10 lg:grid-cols-[1.18fr_0.82fr] lg:gap-16">
              <div className="max-w-2xl">
                {home.aboutGame.paragraphs.map((p) => (
                  <p
                    key={p}
                    className="mt-4 text-lg leading-8 text-muted-foreground first:mt-0"
                  >
                    {renderBoldText(p)}
                  </p>
                ))}
                <Button asChild className="mt-6">
                  <Link href={localizeHref(home.aboutGame.ctaHref, locale)}>
                    {home.aboutGame.cta}
                  </Link>
                </Button>
              </div>
              <div className="rounded-2xl border border-border bg-card/60 p-6">
                <p className="text-sm font-semibold uppercase tracking-[0.2em] text-[hsl(var(--nav-theme))]">
                  {quickFactsLabel}
                </p>
                <dl className="mt-4 divide-y divide-border">
                  {home.aboutGame.stats.map((stat) => (
                    <div
                      key={stat.label}
                      className="flex items-center justify-between py-3 text-base"
                    >
                      <dt className="text-muted-foreground">{stat.label}</dt>
                      <dd className="font-semibold text-foreground">
                        {stat.value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            </div>
          </section>
        );

      case "guideSections":
        return home.guideSections && home.guideSections.length > 0 ? (
          <GuideSectionsBlock sections={home.guideSections} locale={locale} />
        ) : null;

      case "video":
        // Optional — only renders when a video ID is configured
        return home.hero.videoId ? (
          <TrailerButton
            videoId={home.hero.videoId}
            gameName={home.hero.title}
            labels={videoLabels}
          />
        ) : null;

      case "categories":
        // Auto-generated from NAVIGATION_CONFIG, zero extra config
        return categories.length > 0 ? (
          <section className="mx-auto max-w-[1040px]">
            <h2 className="text-center text-3xl font-bold tracking-tight text-foreground sm:text-5xl">
              {home.categories.title}
            </h2>
            <div className="mt-8 flex flex-wrap justify-center gap-4">
              {categories.map((category, index) => {
                const Icon = iconByKey[category.key] ?? BookOpen;
                return (
                  <Fragment key={category.key}>
                    <Link
                      href={localizeHref(category.path, locale)}
                      className="group flex w-full max-w-[19rem] flex-col rounded-2xl border border-border bg-card/70 p-5 transition hover:-translate-y-0.5 hover:border-[hsl(var(--nav-theme-light))]"
                    >
                      <span className="grid h-11 w-11 place-items-center rounded-xl bg-muted text-[hsl(var(--nav-theme))]">
                        <Icon className="h-5 w-5" />
                      </span>
                      <h3 className="mt-4 text-xl font-bold text-foreground group-hover:text-[hsl(var(--nav-theme))]">
                        {category.title}
                      </h3>
                      {category.description ? (
                        <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">
                          {category.description}
                        </p>
                      ) : null}
                      <p className="mt-auto pt-5 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                        {category.count}{" "}
                        {category.count === 1 ? "Article" : "Articles"}
                      </p>
                    </Link>
                    {anyNativeEnabled && index === 3 && categories.length > 4 ? (
                      <div className="basis-full py-4">
                        <NativeFlowAd />
                      </div>
                    ) : null}
                  </Fragment>
                );
              })}
            </div>
          </section>
        ) : null;

      case "featured":
        // The first content decision on the page: route players by the job they
        // need, using real generated articles rather than synthetic tool pages.
        return (
          <LightSectionBlock
            section={home.featured}
            locale={locale}
            insertAd={banner728Enabled || banner300Enabled}
            taskRouter
          />
        );

      case "updates":
        // Compact "what's new" list, title-only rows (not a mini article grid)
        return recentArticles.length > 0 ? (
          <section className="mx-auto max-w-[820px]">
            <h2 className="text-center text-3xl font-bold tracking-tight text-foreground sm:text-5xl">
              {home.updates.title}
            </h2>
            <Card className="mt-8 border-0 bg-transparent p-0 shadow-none">
              <div className="grid gap-3">
                {recentArticles.map((article) => {
                  const articleHref = `/${article.contentType}/${article.slug}`;
                  const categoryLabel = article.contentType
                    .replace(/-/g, " ")
                    .replace(/\b\w/g, (c) => c.toUpperCase());
                  return (
                    <Link
                      key={articleHref}
                      href={localizeHref(articleHref, locale)}
                      className="group flex flex-col gap-3 rounded-2xl border border-border bg-card/70 p-5 transition hover:-translate-y-0.5 hover:border-[hsl(var(--nav-theme-light))] sm:flex-row sm:items-center sm:justify-between"
                    >
                      <span className="flex min-w-0 items-start gap-3 sm:items-center">
                        <Badge className="shrink-0 bg-[hsl(var(--nav-theme))] text-primary-foreground">
                          {categoryLabel}
                        </Badge>
                        <span className="text-lg font-semibold leading-6 text-foreground group-hover:text-[hsl(var(--nav-theme))]">
                          {article.metadata.title}
                        </span>
                      </span>
                      <span className="shrink-0 pl-0 text-sm text-muted-foreground sm:pl-4">
                        {article.metadata.date}
                      </span>
                    </Link>
                  );
                })}
              </div>
              <div className="mt-6 text-center">
                <Button asChild variant="outline">
                  <Link href={localizeHref(home.updates.browseHref, locale)}>
                    {home.updates.browse}
                  </Link>
                </Button>
              </div>
            </Card>
          </section>
        ) : null;

      case "faq":
        // Curated, stays in JSON — answers may contain [label](href) links
        return (
          <section className="mx-auto max-w-[820px]">
            <h2 className="text-center text-3xl font-bold tracking-tight text-foreground sm:text-5xl">
              {home.faq.title}
            </h2>
            <p className="mt-2 text-center text-lg text-muted-foreground">
              {home.faq.description}
            </p>
            <Accordion
              type="single"
              collapsible
              className="mx-auto mt-6 max-w-3xl rounded-2xl border border-border bg-card/70 px-5"
            >
              {home.faq.items.map((item, index) => (
                <AccordionItem key={item.question} value={`item-${index}`}>
                  <AccordionTrigger className="text-left text-lg text-foreground">
                    {item.question}
                  </AccordionTrigger>
                  <AccordionContent className="text-base leading-7 text-muted-foreground">
                    {renderFaqAnswer(item.answer, locale)}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </section>
        );

      case "finalCta":
        // Curated, stays in JSON
        return (
          <section className="mx-auto max-w-[960px] rounded-3xl border border-border bg-gradient-to-br from-muted to-card p-8 text-center sm:p-12">
            <h2 className="text-4xl font-bold tracking-tight text-foreground">
              {home.finalCta.title}
            </h2>
            <p className="mx-auto mt-3 max-w-2xl text-lg text-muted-foreground">
              {home.finalCta.description}
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <Button asChild size="lg">
                <Link href={localizeHref(home.finalCta.primaryHref, locale)}>
                  {home.finalCta.primary}
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link href={localizeHref(home.finalCta.secondaryHref, locale)}>
                  {home.finalCta.secondary}
                </Link>
              </Button>
            </div>
          </section>
        );
    }
  }

  return (
    <div>
      {HOME_SECTION_ORDER.map((section) => {
        const rendered = renderSection(section);
        if (!rendered) return null;
        const spacing =
          section === "hero"
            ? ""
            : section === "ads"
              ? "mt-5 sm:mt-6"
              : "mt-20 sm:mt-24";
        return (
          <div key={section} className={spacing}>
            {rendered}
          </div>
        );
      })}
    </div>
  );
}
