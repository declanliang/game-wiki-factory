import { defineRouting } from "next-intl/routing";
import { PUBLISHED_LOCALES } from "@/config/publication";

/**
 * Generated translations and publicly routable locales are intentionally
 * separate. publication-plan.json controls the release waves.
 *
 * To add a new language you must update THREE places that have to stay in sync:
 *   1. The `locales` array below.
 *   2. The static imports + `messagesMap` in `src/i18n/request.ts`.
 *   3. The matching JSON file in `src/locales/<locale>.json`.
 */
export const routing = defineRouting({
  locales: PUBLISHED_LOCALES,
  defaultLocale: "en",
  // Cloudflare Pages branch: static export has no middleware, so "as-needed"
  // (bare English URLs via a runtime rewrite) isn't possible. Every locale,
  // including English, gets an explicit prefix; public/_redirects 301s the
  // old bare paths (from the Vercel deployment) to /en/... for SEO.
  localePrefix: "always",
  localeDetection: false,
});

export type Locale = (typeof routing.locales)[number];

/**
 * Builds the `alternates.languages` map for Next.js Metadata — one entry per
 * supported locale plus `x-default` pointing at the default-locale URL.
 * `pathname` is locale-agnostic, e.g. "/" or "/guide/some-article".
 */
export function languageAlternates(pathname: string): Record<string, string> {
  const perLocale = routing.locales.map((locale): [string, string] => [locale, `/${locale}${pathname === "/" ? "" : pathname}`]);
  const defaultUrl = perLocale.find(([locale]) => locale === routing.defaultLocale)?.[1] ?? pathname;
  return Object.fromEntries([...perLocale, ["x-default", defaultUrl]]);
}
