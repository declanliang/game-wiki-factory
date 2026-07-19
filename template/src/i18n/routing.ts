import { defineRouting } from "next-intl/routing";

/**
 * Single source of truth for supported locales.
 *
 * To add a new language you must update THREE places that have to stay in sync:
 *   1. The `locales` array below.
 *   2. The static imports + `messagesMap` in `src/i18n/request.ts`.
 *   3. The matching JSON file in `src/locales/<locale>.json`.
 */
export const routing = defineRouting({
  locales: ["en", "es", "de", "fr", "ja", "ko"],
  defaultLocale: "en",
  // English is served without a `/en` prefix (e.g. `/bosses`, `/bosses/gelum`).
  localePrefix: "as-needed",
  // Keep `/` stable as English/x-default. Language changes are explicit via
  // the switcher, avoiding request-header/cookie redirects and private caches.
  localeDetection: false,
});

export type Locale = (typeof routing.locales)[number];

/**
 * Builds the `alternates.languages` map for Next.js Metadata — one entry per
 * supported locale plus `x-default` pointing at the default-locale URL.
 * `pathname` is locale-agnostic, e.g. "/" or "/guide/some-article".
 */
export function languageAlternates(pathname: string): Record<string, string> {
  const perLocale = routing.locales.map((locale): [string, string] => [
    locale,
    locale === routing.defaultLocale ? pathname : `/${locale}${pathname === "/" ? "" : pathname}`,
  ]);
  const defaultUrl = perLocale.find(([locale]) => locale === routing.defaultLocale)?.[1] ?? pathname;
  return Object.fromEntries([...perLocale, ["x-default", defaultUrl]]);
}
