"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, ChevronRight, type LucideIcon } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TrailerButton } from "@/components/trailer";
import { localizeHref } from "@/lib/locale-path";
import { AdSlot } from "@/components/ad-slot";
import { NAVIGATION_CONFIG } from "@/config/navigation";
import { HOME_SECTION_ORDER, type HomeSection } from "@/config/home";
import type { ContentItem } from "@/lib/content";
import en from "@/locales/en.json";

// Lightweight "icon + title + one-line description + link" card item — used by the
// Featured Guides, Live Tools, and Extra Sections blocks. `category` is optional and, when
// it matches a registered NAVIGATION_CONFIG key, borrows that category's icon so games
// don't need a separate icon vocabulary just for these cards.
type LightItem = { title: string; description: string; href: string; category?: string };
// `description` is an optional intro line under the heading — mainly for home.extraSections,
// where a sentence or two of real, keyword-bearing copy above the item cards is the point
// (see doc/homepage-info-schema.md), but any LightSection can use it.
type LightSection = { title: string; description?: string; viewAllHref?: string; viewAllLabel?: string; items: LightItem[] };
type Home = Omit<typeof en.home, "featured" | "liveTools" | "hero"> & {
  hero: Omit<typeof en.home.hero, "videoId"> & { videoId?: string };
  featured: LightSection;
  liveTools?: LightSection;
  // Zero or more additional category-highlight blocks — the homepage's one open-ended
  // extension point, see the HOME_SECTIONS comment in src/config/home.ts.
  extraSections?: LightSection[];
};

type Category = { key: string; path: string; title: string; description: string; count: number };

const iconByKey: Record<string, LucideIcon> = Object.fromEntries(NAVIGATION_CONFIG.map((item) => [item.key, item.icon]));

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
      <Link key={i} href={isExternal ? href : localizeHref(href, locale)} className="font-semibold text-[hsl(var(--nav-theme))] hover:underline">
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
    return <strong key={i} className="font-semibold text-[hsl(var(--nav-theme))]">{match[1]}</strong>;
  });
}

function LightCard({ item, locale }: { item: LightItem; locale: string }) {
  const Icon = (item.category && iconByKey[item.category]) || BookOpen;
  return (
    <Link href={localizeHref(item.href, locale)} className="group flex items-start gap-3 rounded-2xl border border-border bg-card/70 p-4 transition hover:-translate-y-0.5 hover:border-[hsl(var(--nav-theme-light))]">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-muted text-[hsl(var(--nav-theme))]"><Icon className="h-4 w-4" /></span>
      <span className="min-w-0">
        <span className="block text-lg font-semibold text-foreground group-hover:text-[hsl(var(--nav-theme))]">{item.title}</span>
        <span className="mt-1 block text-base leading-6 text-muted-foreground line-clamp-2">{item.description}</span>
      </span>
    </Link>
  );
}

function LightSectionBlock({ section, locale }: { section: LightSection; locale: string }) {
  if (!section.items || section.items.length === 0) return null;
  return (
    <section className="mx-auto max-w-5xl">
      <h2 className="text-center text-5xl font-bold tracking-tight text-foreground">{section.title}</h2>
      {section.description && (
        <p className="mx-auto mt-4 max-w-3xl text-center text-lg text-muted-foreground">{section.description}</p>
      )}
      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {section.items.map((item) => <LightCard key={item.href} item={item} locale={locale} />)}
      </div>
      {section.viewAllHref && (
        <div className="mt-6 text-center">
          <Link href={localizeHref(section.viewAllHref, locale)} className="inline-flex items-center text-base font-semibold text-[hsl(var(--nav-theme))] hover:underline">
            {section.viewAllLabel || "View All"} <ChevronRight className="ml-1 h-4 w-4" />
          </Link>
        </div>
      )}
    </section>
  );
}

export default function HomePageClient({ home, quickFactsLabel, locale, recentArticles, categories }: { home: Home; quickFactsLabel: string; locale: string; recentArticles: ContentItem[]; categories: Category[] }) {
  function renderSection(section: HomeSection) {
    switch (section) {
      case "hero":
        return (
          // Centered eyebrow above H1 → description → 2 CTAs → trust-signal stats. No sidebar, no video here.
          <section className="text-center">
            <div className="mx-auto mb-4 flex justify-center">
              <span className="inline-flex items-center rounded-full border border-[hsl(var(--nav-theme)/0.3)] bg-[hsl(var(--nav-theme)/0.1)] px-3 py-1 text-sm font-semibold text-[hsl(var(--nav-theme))]">{home.hero.eyebrow}</span>
            </div>
            <h1 className="text-5xl font-extrabold tracking-tight text-foreground sm:text-6xl lg:text-7xl">{home.hero.title}</h1>
            <p className="mx-auto mt-5 max-w-3xl text-lg leading-relaxed text-muted-foreground">{home.hero.description}</p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
              <Button asChild size="lg"><Link href={localizeHref(home.hero.primaryCtaHref, locale)}>{home.hero.primaryCta}</Link></Button>
              <Button asChild size="lg" variant="outline"><Link href={home.hero.secondaryCtaHref}>{home.hero.secondaryCta}</Link></Button>
            </div>
            <div className="mx-auto mt-8 grid max-w-3xl grid-cols-2 gap-3 sm:grid-cols-4">
              {home.hero.stats.map((stat) => (
                <div key={stat.label} className="rounded-2xl border border-border bg-card/70 p-5">
                  <p className="text-2xl font-bold text-[hsl(var(--nav-theme))] sm:text-3xl">{stat.value}</p>
                  <p className="mt-2 text-sm text-muted-foreground">{stat.label}</p>
                </div>
              ))}
            </div>
          </section>
        );

      case "ads":
        return (
          <>
            <AdSlot format="banner728x90" className="hidden sm:block" />
            <AdSlot format="mobile320x50" className="sm:hidden" />
          </>
        );

      case "about":
        return (
          // Centered heading + divider, then paragraphs (left) / Quick Facts box (right)
          <section>
            <div className="text-center">
              <h2 className="text-5xl font-bold tracking-tight text-foreground">{home.aboutGame.title}</h2>
              <div className="mx-auto mt-4 h-px w-24 bg-border" />
            </div>
            <div className="mt-8 grid gap-8 lg:grid-cols-[1.3fr_1fr]">
              <div>
                {home.aboutGame.paragraphs.map((p) => <p key={p} className="mt-4 text-lg leading-8 text-muted-foreground first:mt-0">{renderBoldText(p)}</p>)}
                <Button asChild className="mt-6"><Link href={localizeHref(home.aboutGame.ctaHref, locale)}>{home.aboutGame.cta}</Link></Button>
              </div>
              <div className="rounded-2xl border border-border bg-card/60 p-6">
                <p className="text-sm font-semibold uppercase tracking-[0.2em] text-[hsl(var(--nav-theme))]">{quickFactsLabel}</p>
                <dl className="mt-4 divide-y divide-border">
                  {home.aboutGame.stats.map((stat) => (
                    <div key={stat.label} className="flex items-center justify-between py-3 text-base">
                      <dt className="text-muted-foreground">{stat.label}</dt>
                      <dd className="font-semibold text-foreground">{stat.value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </div>
          </section>
        );

      case "video":
        // Optional — only renders when a video ID is configured
        return home.hero.videoId ? (
          <section className="mx-auto max-w-4xl">
            <TrailerButton videoId={home.hero.videoId} gameName={home.hero.title} />
          </section>
        ) : null;

      case "categories":
        // Auto-generated from NAVIGATION_CONFIG, zero extra config
        return categories.length > 0 ? (
          <section className="mx-auto max-w-5xl">
            <h2 className="text-center text-5xl font-bold tracking-tight text-foreground">{home.categories.title}</h2>
            <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {categories.map((category) => {
                const Icon = iconByKey[category.key] ?? BookOpen;
                return (
                  <Link key={category.key} href={localizeHref(category.path, locale)} className="group rounded-2xl border border-border bg-card/70 p-5 transition hover:-translate-y-0.5 hover:border-[hsl(var(--nav-theme-light))]">
                    <span className="grid h-11 w-11 place-items-center rounded-xl bg-muted text-[hsl(var(--nav-theme))]"><Icon className="h-5 w-5" /></span>
                    <h3 className="mt-4 text-xl font-bold text-foreground group-hover:text-[hsl(var(--nav-theme))]">{category.title}</h3>
                    <p className="mt-4 text-sm font-semibold uppercase tracking-wide text-muted-foreground">{category.count} {category.count === 1 ? "Article" : "Articles"}</p>
                  </Link>
                );
              })}
            </div>
          </section>
        ) : null;

      case "featured":
        // Lightweight editor-picked cards, pointing at specific articles (not a repeat of the category cards above)
        return <LightSectionBlock section={home.featured} locale={locale} />;

      case "liveTools":
        // Only renders if the game actually has time-sensitive content configured
        return home.liveTools ? <LightSectionBlock section={home.liveTools} locale={locale} /> : null;

      case "extraSections":
        // Zero or more editor-provided blocks (e.g. one per major content category) — each
        // one independently hides itself via LightSectionBlock if it has no items, so a
        // partially-filled array degrades gracefully instead of leaving gaps.
        return home.extraSections && home.extraSections.length > 0 ? (
          <div className="space-y-16">
            {home.extraSections.map((section, i) => (
              <LightSectionBlock key={section.title || i} section={section} locale={locale} />
            ))}
          </div>
        ) : null;

      case "updates":
        // Compact "what's new" list, title-only rows (not a mini article grid)
        return recentArticles.length > 0 ? (
          <section>
            <h2 className="text-center text-5xl font-bold tracking-tight text-foreground">{home.updates.title}</h2>
            <Card className="mt-6 border-border bg-card/70 p-5">
              <div className="divide-y divide-border">
                {recentArticles.map((article) => {
                  const articleHref = `/${article.contentType}/${article.slug}`;
                  const categoryLabel = article.contentType.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
                  return (
                    <Link key={articleHref} href={localizeHref(articleHref, locale)} className="group flex items-center justify-between gap-4 py-3.5">
                      <span className="flex min-w-0 items-center gap-3">
                        <Badge className="shrink-0 bg-[hsl(var(--nav-theme))] text-primary-foreground">{categoryLabel}</Badge>
                        <span className="truncate text-lg font-semibold text-foreground group-hover:text-[hsl(var(--nav-theme))]">{article.metadata.title}</span>
                      </span>
                      <span className="shrink-0 text-sm text-muted-foreground">{article.metadata.date}</span>
                    </Link>
                  );
                })}
              </div>
              <Button asChild className="mt-5 w-full" variant="outline">
                <Link href={localizeHref(home.updates.browseHref, locale)}>{home.updates.browse}</Link>
              </Button>
            </Card>
          </section>
        ) : null;

      case "faq":
        // Curated, stays in JSON — answers may contain [label](href) links
        return (
          <section>
            <h2 className="text-center text-5xl font-bold tracking-tight text-foreground">{home.faq.title}</h2>
            <p className="mt-2 text-center text-lg text-muted-foreground">{home.faq.description}</p>
            <Accordion type="single" collapsible className="mx-auto mt-6 max-w-3xl rounded-2xl border border-border bg-card/70 px-5">
              {home.faq.items.map((item, index) => (
                <AccordionItem key={item.question} value={`item-${index}`}>
                  <AccordionTrigger className="text-left text-lg text-foreground">{item.question}</AccordionTrigger>
                  <AccordionContent className="text-base leading-7 text-muted-foreground">{renderFaqAnswer(item.answer, locale)}</AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </section>
        );

      case "finalCta":
        // Curated, stays in JSON
        return (
          <section className="rounded-3xl border border-border bg-gradient-to-br from-muted to-card p-8 text-center">
            <h2 className="text-4xl font-bold tracking-tight text-foreground">{home.finalCta.title}</h2>
            <p className="mx-auto mt-3 max-w-2xl text-lg text-muted-foreground">{home.finalCta.description}</p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <Button asChild size="lg"><Link href={localizeHref(home.finalCta.primaryHref, locale)}>{home.finalCta.primary}<ArrowRight className="ml-2 h-4 w-4" /></Link></Button>
              <Button asChild size="lg" variant="outline"><Link href={localizeHref(home.finalCta.secondaryHref, locale)}>{home.finalCta.secondary}</Link></Button>
            </div>
          </section>
        );
    }
  }

  return (
    <div className="space-y-16">
      {HOME_SECTION_ORDER.map((section) => {
        const rendered = renderSection(section);
        return rendered ? <div key={section}>{rendered}</div> : null;
      })}
    </div>
  );
}
