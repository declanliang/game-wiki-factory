// Pure, dependency-free helper — deliberately kept out of site.tsx so client components
// (HomePageClient.tsx, header-nav.tsx) can import it without pulling in site.tsx's
// server-only imports (e.g. getDynamicNavigation, which touches Node's `fs`) into the
// client bundle.
export function localizeHref(href: string, locale: string) {
  if (/^([a-z][a-z0-9+.-]*:)?\/\//i.test(href)) return href;
  if (locale === "en") return href;
  return `/${locale}${href === "/" ? "" : href}`;
}
