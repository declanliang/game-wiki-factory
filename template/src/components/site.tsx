import Link from "next/link";
import { ChevronRight, ExternalLink, Menu } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { NAVIGATION_CONFIG } from "@/config/navigation";
import {
  CONTENT_TYPES,
  getDynamicNavigation,
  type NavGroup,
} from "@/lib/content";
import type { Locale } from "@/i18n/routing";
import { localizeHref } from "@/lib/locale-path";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { CollapsibleNavGroup } from "@/components/collapsible-nav-group";
import { AdSlot } from "@/components/ad-slot";
import { LanguageSwitcher } from "@/components/language-switcher";
import { HeaderNavLinks } from "@/components/header-nav";

export async function SiteHeader({ locale }: { locale: string }) {
  const t = await getTranslations({ locale, namespace: "nav" });
  const site = await getTranslations({ locale, namespace: "site" });
  const shared = await getTranslations({ locale, namespace: "shared" });
  const shortName = site("shortName");
  const playUrl = site("playUrl");
  // Cheap sync fs scan (regex title extraction, no dynamic import) — safe to call on every
  // page since it's the same function WikiSidebar already uses for nav/detail pages.
  const navGroupsByKey = Object.fromEntries(
    getDynamicNavigation(locale as Locale).map((group) => [group.slug, group]),
  );
  const navItems = NAVIGATION_CONFIG.map((item) => {
    const group = navGroupsByKey[item.key] as NavGroup | undefined;
    // links[0] is the "Overview" entry (see getDynamicNavigation) — skip it for the article preview.
    const articles = group?.links
      .slice(1)
      .map((link) => ({ label: link.label, href: link.href }));
    return {
      key: item.key,
      path: item.path,
      label: t(item.key),
      articles,
      readMoreLabel: shared("readMore"),
    };
  });
  const header = (
    <div className="flex items-center justify-between gap-4">
      <Link
        href={localizeHref("/", locale)}
        className="flex items-center gap-3"
      >
        <span className="grid h-9 w-9 place-items-center rounded-xl border border-border bg-muted text-sm font-black text-foreground">
          {shortName.slice(0, 2).toUpperCase()}
        </span>
        <span className="text-sm font-bold tracking-wide text-foreground">
          {site("name")}
        </span>
      </Link>
      <HeaderNavLinks
        items={navItems}
        locale={locale}
        className="hidden items-center gap-1 md:flex"
        linkClassName="rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground"
        activeClassName="bg-muted text-foreground"
      />
      <div className="flex items-center gap-2">
        <LanguageSwitcher locale={locale} />
        <Sheet>
          <SheetTrigger asChild className="md:hidden">
            <Button variant="outline" size="icon" aria-label={t("menu")}>
              <Menu className="h-4 w-4" />
            </Button>
          </SheetTrigger>
          <SheetContent className="border-border bg-background text-foreground">
            <SheetTitle className="sr-only">{t("menu")}</SheetTitle>
            <SheetDescription className="sr-only">
              {site("name")}
            </SheetDescription>
            <div className="mt-8 grid gap-2">
              {NAVIGATION_CONFIG.map((item) => (
                <Link
                  key={item.key}
                  href={localizeHref(item.path, locale)}
                  className="rounded-lg px-3 py-3 text-sm font-semibold hover:bg-muted"
                >
                  {t(item.key)}
                </Link>
              ))}
              <Link
                href={playUrl}
                className="rounded-lg bg-[hsl(var(--nav-theme))] px-3 py-3 text-sm font-semibold text-primary-foreground"
              >
                {t("playCta")}
              </Link>
            </div>
          </SheetContent>
        </Sheet>
      </div>
    </div>
  );
  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/90 backdrop-blur-xl">
      <div className="mx-auto max-w-[1280px] px-5 py-3 sm:px-8 lg:px-10">
        {header}
      </div>
    </header>
  );
}

export async function WikiSidebar({
  locale,
  navGroups,
  currentPath,
}: { locale: string; navGroups: NavGroup[]; currentPath?: string }) {
  const t = await getTranslations({ locale, namespace: "shared" });
  const isActive = (href: string) => currentPath === href;
  const hasCodes = CONTENT_TYPES.includes("codes");
  const activeCodes = hasCodes
    ? (t.raw("activeCodesList") as { code: string; reward: string }[])
    : [];
  return (
    <aside className="hidden space-y-6 lg:sticky lg:top-24 lg:block lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto lg:pr-1">
      <section className="rounded-2xl border border-border bg-card/60 p-5 shadow-sm">
        <h3 className="mb-4 text-xs font-bold uppercase tracking-[0.22em] text-muted-foreground">
          {t("wikiNavigation")}
        </h3>
        <div className="space-y-4">
          {navGroups.map((group) => (
            <CollapsibleNavGroup
              key={group.slug}
              title={group.title}
              icon={
                <span className="grid h-4 w-4 place-items-center rounded text-[10px] font-bold text-[hsl(var(--nav-theme))]">
                  {group.title[0]}
                </span>
              }
              count={group.count}
              currentPath={currentPath}
            >
              <ul className="space-y-1">
                {group.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={localizeHref(link.href, locale)}
                      className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors ${isActive(link.href) ? "bg-[hsl(var(--nav-theme)/0.15)] font-semibold text-[hsl(var(--nav-theme))]" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}
                    >
                      <span className="truncate">{link.label}</span>
                      {link.badge && (
                        <Badge
                          variant="secondary"
                          className="ml-auto h-5 border-border px-1.5 text-[10px]"
                        >
                          {link.badge}
                        </Badge>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            </CollapsibleNavGroup>
          ))}
        </div>
      </section>
      {hasCodes ? (
        <section className="rounded-2xl border border-border bg-card/60 p-5">
          <h3 className="mb-3 text-sm font-bold text-foreground">
            {t("activeCodes")}
          </h3>
          <div className="space-y-3 text-sm">
            {activeCodes.length > 0 ? (
              activeCodes.map((c) => (
                <div key={c.code} className="rounded-xl bg-muted p-3">
                  <code className="font-bold text-foreground">{c.code}</code>
                  <p className="mt-1 text-muted-foreground">{c.reward}</p>
                </div>
              ))
            ) : (
              <p className="text-muted-foreground">{t("noCodesAvailable")}</p>
            )}
            <Link
              href={localizeHref("/codes", locale)}
              className="inline-flex items-center gap-1 text-sm font-semibold text-[hsl(var(--nav-theme))]"
            >
              {t("viewAllCodes")} <ChevronRight className="h-4 w-4" />
            </Link>
          </div>
        </section>
      ) : null}
      <AdSlot format="sidebar160x600" />
    </aside>
  );
}

// Placeholder social hrefs (e.g. "https://discord.gg/REPLACE-WITH-REAL-INVITE") shouldn't be
// rendered as if they were real links — until the site owner fills in the real URL, the
// bottom social bar just quietly omits that entry instead of linking nowhere.
function isPlaceholderHref(href: string) {
  return href.includes("REPLACE-WITH");
}

export async function SiteFooter({ locale }: { locale: string }) {
  const t = await getTranslations({ locale, namespace: "footer" });
  const site = await getTranslations({ locale, namespace: "site" });
  const nav = await getTranslations({ locale, namespace: "nav" });
  const legal = await getTranslations({ locale, namespace: "legal" });
  // Content-type links are derived from NAVIGATION_CONFIG, not hardcoded —
  // adding/removing a category here automatically updates the footer.
  const contentLinks: string[][] = NAVIGATION_CONFIG.filter(
    (item) => item.isContentType,
  ).map((item) => [nav(item.key), item.path]);
  const legalLinks: string[][] = [
    [t("aboutTitle"), "/about"],
    [legal("copyright.title"), "/copyright"],
    [t("privacyPolicy"), "/privacy-policy"],
    [t("termsOfService"), "/terms-of-service"],
  ];
  // "Open on Roblox" is dropped here — it's already the primary/secondary CTA in the Hero and
  // Final CTA sections above, repeating it a third time in the footer added nothing.
  const socialLinks: string[][] = [
    [t("officialDiscord"), t("officialDiscordHref")],
    [t("officialYoutube"), t("officialYoutubeHref")],
    [t("communityTool"), t("communityToolHref")],
  ].filter(([, href]) => !isPlaceholderHref(href));
  return (
    <footer className="mt-16 border-t border-border bg-card/30">
      <div className="mx-auto max-w-[1200px] px-5 py-10 sm:px-8 lg:px-10">
        <div className="grid gap-8 md:grid-cols-4">
          <div className="md:col-span-2">
            <h3 className="font-bold text-foreground">{t("aboutTitle")}</h3>
            <p className="mt-3 max-w-xl text-sm leading-7 text-muted-foreground">
              {t("about")}
            </p>
            {/* Disclaimer shown once here instead of duplicated in a top banner + the copyright line */}
            <p className="mt-3 text-xs font-semibold uppercase tracking-[0.15em] text-muted-foreground">
              {site("legalNotice")}
            </p>
          </div>
          <FooterList locale={locale} title="Wiki" links={contentLinks} />
          <FooterList locale={locale} title={t("legal")} links={legalLinks} />
        </div>
        <div className="mt-10 border-t border-border pt-6">
          {socialLinks.length > 0 && (
            <div className="mb-4 flex flex-wrap justify-center gap-3">
              {socialLinks.map(([label, href]) => (
                <Link
                  key={href}
                  href={href}
                  className="inline-flex items-center gap-1.5 rounded-full border border-border px-4 py-1.5 text-sm font-medium text-muted-foreground transition hover:border-[hsl(var(--nav-theme-light))] hover:text-foreground"
                >
                  {label} <ExternalLink className="h-3.5 w-3.5" />
                </Link>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-4">
            <p className="text-xs text-muted-foreground">{t("copyright")}</p>
            <LanguageSwitcher locale={locale} />
          </div>
        </div>
      </div>
    </footer>
  );
}

function FooterList({
  title,
  links,
  locale,
}: { title: string; links: string[][]; locale: string }) {
  return (
    <div>
      <h4 className="font-semibold text-foreground">{title}</h4>
      <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
        {links.map(([label, href]) => (
          <li key={href}>
            <Link
              className="hover:text-foreground"
              href={localizeHref(href, locale)}
            >
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
