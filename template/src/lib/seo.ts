import type { Metadata } from "next";
import { getSiteName, localizedSiteUrl, SITE_LOGO_URL, SITE_OG_IMAGE_URL, SITE_URL } from "@/config/site";
import { routing } from "@/i18n/routing";
import type en from "@/locales/en.json";

type Messages = typeof en;

const DANGLING_CONNECTOR_RE =
  /\s+(?:&|and|or|with|for|to|vs\.?|und|oder|mit|für|y|o|con|para|et|ou|avec|pour)$/i;

function metadataLimit(locale: string, kind: "title" | "description"): number {
  const cjk = locale === "ja" || locale === "ko" || locale === "zh";
  if (kind === "title") return cjk ? 36 : 60;
  return cjk ? 90 : 160;
}

function compactMetadataText(value: string, limit: number, locale: string): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= limit) return normalized;
  const cjk = locale === "ja" || locale === "ko" || locale === "zh";
  let candidate = normalized.slice(0, limit);
  if (!cjk && candidate.includes(" ")) {
    candidate = candidate.replace(/\s+\S*$/, "");
  }
  candidate = candidate
    .replace(DANGLING_CONNECTOR_RE, "")
    .replace(/[\s,;:–—&-]+$/u, "")
    .trim();
  return candidate || normalized.slice(0, limit).trim();
}

/** Last-mile guard for metadata produced by upstream content stages. */
export function normalizeMetadataTitle(value: string, locale: string): string {
  return compactMetadataText(value, metadataLimit(locale, "title"), locale);
}

export function normalizeMetadataDescription(value: string, locale: string): string {
  return compactMetadataText(value, metadataLimit(locale, "description"), locale);
}

export function buildCategoryMetadataTitle(
  categoryTitle: string,
  gameName: string,
  siteName: string,
  locale: string,
): string {
  const full = `${categoryTitle} — ${siteName}`;
  if (full.length <= metadataLimit(locale, "title")) return full;
  return normalizeMetadataTitle(`${gameName} ${categoryTitle}`, locale);
}

/**
 * Next.js Metadata merging replaces `openGraph`/`twitter` wholesale when a
 * route segment defines its own — it does not deep-merge with the parent
 * layout's values. Every generateMetadata() that sets openGraph must
 * therefore include type/locale/siteName itself; this helper keeps that
 * consistent instead of re-typing it at each call site.
 */
export function buildOpenGraph({
  locale,
  title,
  description,
  url,
  images,
  type = "website",
  siteName,
}: {
  locale: string;
  title: string;
  description: string;
  url: string;
  images?: string[];
  type?: "website" | "article";
  siteName: string;
}): NonNullable<Metadata["openGraph"]> {
  return {
    type,
    locale,
    siteName,
    title,
    description,
    url,
    images: (images ?? [SITE_OG_IMAGE_URL]).map((src) => ({ url: src })),
  };
}

export function buildTwitter({
  title,
  description,
  images,
}: {
  title: string;
  description: string;
  images?: string[];
}): NonNullable<Metadata["twitter"]> {
  return { card: "summary_large_image", title, description, images: images ?? [SITE_OG_IMAGE_URL] };
}

/**
 * Site-wide JSON-LD @graph: WebSite + Organization, cross-referenced by @id
 * so Google can associate them, plus an optional VideoGame entity built only
 * from facts actually provided in site config (genre/gamePlatform/datePublished/
 * price/developer) — any missing field is simply omitted, never guessed.
 */
export function buildSiteGraph(messages: Pick<Messages, "site">, locale: string) {
  const siteName = getSiteName(messages);
  const localeUrl = localizedSiteUrl("/", locale);
  const websiteId = `${localeUrl}#website`;
  const orgId = `${SITE_URL}/#organization`;
  const gameId = `${SITE_URL}/#game`;

  const website = {
    "@type": "WebSite",
    "@id": websiteId,
    name: siteName,
    url: localeUrl,
    description: messages.site.description,
    inLanguage: locale,
    publisher: { "@id": orgId },
    about: { "@id": gameId },
  };

  const organization = {
    "@type": "Organization",
    "@id": orgId,
    name: siteName,
    url: SITE_URL,
    logo: { "@type": "ImageObject", url: SITE_LOGO_URL },
  };

  const { genre, gamePlatform, datePublished, price, priceCurrency, developer, playUrl } = messages.site as Messages["site"] & {
    genre?: string[];
    gamePlatform?: string[];
    datePublished?: string;
    price?: string;
    priceCurrency?: string;
    developer?: string;
  };
  const hasGameFacts = Boolean((genre && genre.length) || (gamePlatform && gamePlatform.length) || datePublished || price || developer);

  const videoGame = hasGameFacts
    ? {
        "@type": "VideoGame",
        "@id": gameId,
        name: messages.site.name,
        description: messages.site.description,
        ...(genre && genre.length ? { genre } : {}),
        ...(gamePlatform && gamePlatform.length ? { gamePlatform } : {}),
        ...(datePublished ? { datePublished } : {}),
        ...(developer ? { author: { "@type": "Organization", name: developer }, publisher: { "@type": "Organization", name: developer } } : {}),
        ...buildOffer(price, priceCurrency, playUrl),
      }
    : null;

  return { "@context": "https://schema.org", "@graph": [website, organization, ...(videoGame ? [videoGame] : [])] };
}

/**
 * Vercel sets VERCEL_ENV automatically (production/preview/development) —
 * only Preview/dev deployments get noindex'd; other hosts (Docker/Netlify)
 * never set this var, so `shouldIndex()` returns true there and this is a no-op.
 */
export function shouldIndex(): boolean {
  const env = process.env.VERCEL_ENV;
  return !env || env === "production";
}

function buildOffer(price: string | undefined, priceCurrency: string | undefined, url: string) {
  if (!price) return {};
  if (price.toLowerCase() === "free" || price === "0") return { isAccessibleForFree: true };
  return { offers: { "@type": "Offer", price, ...(priceCurrency ? { priceCurrency } : {}), availability: "https://schema.org/InStock", url } };
}
