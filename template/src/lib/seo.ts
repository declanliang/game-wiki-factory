import type { Metadata } from "next";
import { getSiteName, localizedSiteUrl, SITE_LOGO_URL, SITE_OG_IMAGE_URL, SITE_URL } from "@/config/site";
import type en from "@/locales/en.json";

type Messages = typeof en;

const DANGLING_CONNECTOR_RE =
  /\s+(?:&|and|or|with|for|to|vs\.?|the|a|an|in|on|at|of|from|into|this|that|your|our|und|oder|mit|für|y|o|con|para|et|ou|avec|pour)$/i;

function metadataLimit(locale: string, kind: "title" | "description"): number {
  const cjk = locale === "ja" || locale === "ko" || locale === "zh";
  if (kind === "title") return cjk ? 36 : 60;
  return cjk ? 90 : 160;
}

function compactMetadataText(value: string, limit: number, locale: string, sentence = false): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  const cjk = locale === "ja" || locale === "ko" || locale === "zh";
  let candidate = normalized.length > limit ? normalized.slice(0, limit) : normalized;
  if (normalized.length > limit && !cjk && candidate.includes(" ")) {
    candidate = candidate.replace(/\s+\S*$/, "");
  }
  let cleaned = (sentence ? candidate.replace(/[.!?]+$/u, "") : candidate).trim();
  while (DANGLING_CONNECTOR_RE.test(cleaned)) {
    cleaned = cleaned.replace(DANGLING_CONNECTOR_RE, "").trim();
  }
  cleaned = cleaned.replace(/[\s,;:–—&-]+$/u, "").trim();
  if (!cleaned) return normalized.slice(0, limit).trim();
  if (sentence && (cleaned !== normalized || /[.!?]$/u.test(normalized))) return `${cleaned}.`;
  return cleaned;
}

/** Last-mile guard for metadata produced by upstream content stages. */
export function normalizeMetadataTitle(value: string, locale: string): string {
  return compactMetadataText(value, metadataLimit(locale, "title"), locale);
}

export function normalizeMetadataDescription(value: string, locale: string): string {
  return compactMetadataText(value, metadataLimit(locale, "description"), locale, true);
}

export function buildCategoryMetadataTitle(
  categoryTitle: string,
  gameName: string,
  siteName: string,
  locale: string,
): string {
  const full = `${categoryTitle} — ${siteName}`;
  if (full.length <= metadataLimit(locale, "title")) return full;
  const compact = `${categoryTitle} | ${gameName}`;
  return compact.length <= metadataLimit(locale, "title") ? compact : categoryTitle;
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

  const { genre, gamePlatform, datePublished, price, priceCurrency, developer, publisher, playUrl } = messages.site as Messages["site"] & {
    genre?: string[];
    gamePlatform?: string[];
    datePublished?: string;
    price?: string;
    priceCurrency?: string;
    developer?: string;
    publisher?: string;
  };
  const hasGameFacts = Boolean((genre && genre.length) || (gamePlatform && gamePlatform.length) || datePublished || price || developer || publisher);

  const videoGame = hasGameFacts
    ? {
        "@type": "VideoGame",
        "@id": gameId,
        name: messages.site.name,
        description: messages.site.description,
        ...(genre && genre.length ? { genre } : {}),
        ...(gamePlatform && gamePlatform.length ? { gamePlatform } : {}),
        ...(datePublished ? { datePublished } : {}),
        ...(developer ? { author: { "@type": "Organization", name: developer } } : {}),
        ...(publisher ? { publisher: { "@type": "Organization", name: publisher } } : {}),
        ...buildOffer(price, priceCurrency, playUrl),
      }
    : null;

  return { "@context": "https://schema.org", "@graph": [website, organization, ...(videoGame ? [videoGame] : [])] };
}

/**
 * Git-integrated Cloudflare Pages used CF_PAGES_BRANCH. Workers Static Assets
 * builds are run by Factory for production, so no branch variable means indexable.
 */
export function shouldIndex(): boolean {
  const branch = process.env.CF_PAGES_BRANCH;
  const productionBranch = process.env.CF_PAGES_PRODUCTION_BRANCH || "main";
  return !branch || branch === productionBranch;
}

function buildOffer(price: string | undefined, priceCurrency: string | undefined, url: string) {
  if (!price) return {};
  if (price.toLowerCase() === "free" || price === "0") return { isAccessibleForFree: true };
  return { offers: { "@type": "Offer", price, ...(priceCurrency ? { priceCurrency } : {}), availability: "https://schema.org/InStock", url } };
}
