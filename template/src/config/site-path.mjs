export function normalizePathname(pathname = "/") {
  const raw = String(pathname || "/").trim();
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(raw)) {
    throw new Error(`Expected a site-relative pathname, received ${raw}`);
  }
  const normalized = `/${raw}`.replace(/\/{2,}/g, "/");
  return normalized.length > 1 ? normalized.replace(/\/$/, "") : normalized;
}

export function localizedPathname(pathname, locale) {
  // Static export: every locale (including the default) is prefixed —
  // static export has no middleware to rewrite "/" to "/en" at request time.
  const normalized = normalizePathname(pathname);
  if (!locale) return normalized;
  return `/${locale}${normalized === "/" ? "" : normalized}`;
}

export function absoluteLocalizedUrl(origin, pathname, locale) {
  const cleanOrigin = new URL(origin).origin;
  const localized = localizedPathname(pathname, locale);
  return `${cleanOrigin}${localized === "/" ? "" : localized}`;
}
