export const DEFAULT_SITE_URL = "https://example.com";

export function resolveSiteUrl(value) {
  const configured = value?.trim() || DEFAULT_SITE_URL;
  const explicitScheme = configured.match(/^([a-z][a-z0-9+.-]*):\/\//i);
  const hasScheme = /^[a-z][a-z0-9+.-]*:/i.test(configured);
  const looksLikeHostPort = /^[a-z0-9.-]+:\d+(?:[/?#]|$)/i.test(configured);
  if (hasScheme && !looksLikeHostPort && !/^https?:\/\//i.test(configured)) {
    throw new Error("NEXT_PUBLIC_SITE_URL must use http:// or https://");
  }

  const absolute = explicitScheme ? configured : `https://${configured}`;
  let parsed;
  try {
    parsed = new URL(absolute);
  } catch {
    throw new Error(
      "NEXT_PUBLIC_SITE_URL must be a valid hostname or absolute HTTP(S) URL",
    );
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("NEXT_PUBLIC_SITE_URL must use http:// or https://");
  }
  if (!parsed.hostname || /\s/.test(parsed.hostname)) {
    throw new Error("NEXT_PUBLIC_SITE_URL must contain a valid hostname");
  }
  return parsed.origin;
}

export function resolveDeploymentSiteUrl(env) {
  return resolveSiteUrl(env.NEXT_PUBLIC_SITE_URL);
}
