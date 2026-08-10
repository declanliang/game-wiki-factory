/**
 * Keep heading IDs identical between the server-side TOC extractor and the
 * MDX renderer. Unicode letters/numbers are preserved for Spanish, French,
 * German and Japanese headings; empty results receive a stable fallback.
 */
export function slugifyHeading(value: string): string {
  const normalized = value.normalize("NFKC").toLocaleLowerCase().trim();
  const slug = normalized
    .replace(/[^\p{L}\p{N}\s-]+/gu, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  if (slug) return slug;

  let hash = 0;
  for (const char of value) hash = (hash * 31 + char.codePointAt(0)!) >>> 0;
  return `section-${hash.toString(36)}`;
}
