import type en from "@/locales/en.json";
import { resolveDeploymentSiteUrl } from "./site-url.mjs";
import { absoluteLocalizedUrl } from "./site-path.mjs";

/**
 * Single source of truth for deployment-level site constants.
 * The game/brand name itself lives in src/locales/<locale>.json under "site" —
 * see getSiteName() below. Swap those, not this file, when reusing this codebase.
 */

export const SITE_URL = resolveDeploymentSiteUrl(process.env);

export const SITE_LOGO_PATH = "/android-chrome-512x512.png";
export const SITE_OG_IMAGE_PATH = "/images/hero.webp";

export const SITE_LOGO_URL = `${SITE_URL}${SITE_LOGO_PATH}`;
export const SITE_OG_IMAGE_URL = `${SITE_URL}${SITE_OG_IMAGE_PATH}`;

export function localizedSiteUrl(pathname: string, locale: string): string {
  return absoluteLocalizedUrl(SITE_URL, pathname, locale);
}

type Messages = typeof en;

/** "{shortName} Wiki" — used for <title>, og:site_name, and every JSON-LD name field. */
export function getSiteName(messages: Pick<Messages, "site">): string {
  return `${messages.site.shortName} Wiki`;
}
