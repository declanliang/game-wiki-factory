import type { MetadataRoute } from "next";
import { CONTENT_TYPES } from "@/config/navigation";
import { SITE_URL } from "@/config/site";
import { getAllContent } from "@/lib/content";
import { languageAlternates, routing } from "@/i18n/routing";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // Legal / info pages that always exist regardless of game — we don't know when
  // their content last meaningfully changed, so lastModified is omitted rather
  // than guessed (Next.js treats it as optional).
  const legalPaths = ["/about", "/privacy-policy", "/terms-of-service", "/copyright"];

  // Article entries + per-category freshness, keyed off content that actually
  // exists under content/<locale>/<type>/ (default locale is the source of truth
  // for which categories/articles exist at all).
  const articleEntries: { path: string; lastModified: Date }[] = [];
  const latestByType: Record<string, Date> = {};
  for (const contentType of CONTENT_TYPES) {
    const items = await getAllContent(contentType, routing.defaultLocale);
    for (const item of items) {
      const dateStr = item.metadata.lastModified ?? item.metadata.date;
      const lastModified = new Date(dateStr);
      articleEntries.push({ path: `/${contentType}/${item.slug}`, lastModified });
      if (!latestByType[contentType] || lastModified > latestByType[contentType]) latestByType[contentType] = lastModified;
    }
  }

  // Empty categories (e.g. an unused generic default like "wiki") are thin/soft-404
  // candidates — don't submit them for indexing. The page itself still exists and
  // returns 200 (see [...slug]/page.tsx's noindex-when-empty), just not in the sitemap.
  const listPaths = CONTENT_TYPES.filter((ct) => latestByType[ct]).map((ct) => `/${ct}`);
  const mostRecentOverall = Object.values(latestByType).reduce<Date | undefined>((max, d) => (!max || d > max ? d : max), undefined);

  const staticEntries: { path: string; lastModified?: Date }[] = [
    { path: "/", lastModified: mostRecentOverall },
    ...listPaths.map((path) => ({ path, lastModified: latestByType[path.slice(1)] })),
    ...legalPaths.map((path) => ({ path, lastModified: undefined })),
  ];

  const allEntries: { path: string; lastModified?: Date }[] = [...staticEntries, ...articleEntries];

  return routing.locales.flatMap((locale) =>
    allEntries.map(({ path, lastModified }) => ({
      url: `${SITE_URL}${locale === routing.defaultLocale ? "" : `/${locale}`}${path === "/" ? "" : path}`,
      ...(lastModified ? { lastModified } : {}),
      changeFrequency: path === "/" ? ("daily" as const) : listPaths.includes(path) ? ("weekly" as const) : legalPaths.includes(path) ? ("monthly" as const) : ("weekly" as const),
      priority: path === "/" ? 1 : listPaths.includes(path) ? 0.8 : legalPaths.includes(path) ? 0.3 : 0.6,
      // Sitemap hreflang must be fully-qualified (unlike the HTML <link> version,
      // which is relative) — Google ignores relative URLs here.
      alternates: { languages: Object.fromEntries(Object.entries(languageAlternates(path)).map(([loc, href]) => [loc, `${SITE_URL}${href}`])) },
    })),
  );
}
