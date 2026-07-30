import "server-only";

import { AD_FORMATS, type AdAvailability, type AdFormat } from "@/lib/ad-types";

function decodeSnippet(encoded: string | undefined): string | undefined {
  if (!encoded?.trim()) return undefined;
  try {
    return Buffer.from(encoded.trim(), "base64").toString("utf8").trim() || undefined;
  } catch {
    return undefined;
  }
}

const snippets: Record<AdFormat, string | undefined> = {
  nativeBanner: decodeSnippet(process.env.AD_NATIVE_BANNER_B64),
  nativeBannerMobile: decodeSnippet(process.env.AD_NATIVE_BANNER_MOBILE_B64),
  banner728x90: decodeSnippet(process.env.AD_BANNER_728X90_B64),
  banner300x250: decodeSnippet(process.env.AD_BANNER_300X250_B64),
  banner468x60: decodeSnippet(process.env.AD_BANNER_468X60_B64),
  sidebar160x600: decodeSnippet(process.env.AD_SIDEBAR_160X600_B64),
  sidebar160x300: decodeSnippet(process.env.AD_SIDEBAR_160X300_B64),
  mobile320x50: decodeSnippet(process.env.AD_MOBILE_320X50_B64),
};

export function isAdFormat(value: string): value is AdFormat {
  return (AD_FORMATS as readonly string[]).includes(value);
}

export function getAdSnippet(format: AdFormat): string | undefined {
  return snippets[format]?.trim() || undefined;
}

export function getAdAvailability(): AdAvailability {
  return Object.fromEntries(AD_FORMATS.map((format) => [format, Boolean(getAdSnippet(format))])) as AdAvailability;
}
