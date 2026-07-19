export function normalizePathname(pathname = "/") {
  const raw = String(pathname || "/").trim();
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(raw)) {
    throw new Error(`Expected a site-relative pathname, received ${raw}`);
  }
  const normalized = `/${raw}`.replace(/\/{2,}/g, "/");
  return normalized.length > 1 ? normalized.replace(/\/$/, "") : normalized;
}

export function localizedPathname(pathname, locale, defaultLocale = "en") {
  const normalized = normalizePathname(pathname);
  if (!locale || locale === defaultLocale) return normalized;
  return `/${locale}${normalized === "/" ? "" : normalized}`;
}

export function absoluteLocalizedUrl(origin, pathname, locale, defaultLocale = "en") {
  const cleanOrigin = new URL(origin).origin;
  const localized = localizedPathname(pathname, locale, defaultLocale);
  return `${cleanOrigin}${localized === "/" ? "" : localized}`;
}
