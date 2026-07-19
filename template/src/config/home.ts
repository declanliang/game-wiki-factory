// Ordered list of homepage sections. Reorder or remove entries to recompose the homepage
// for a given game without touching HomePageClient.tsx — the switch statement there still
// owns each section's own conditional visibility (e.g. "video" only renders when
// home.hero.videoId is set, "liveTools"/"extraSections" only when that data exists in
// en.json), so removing a section here just means "never render it even if the underlying
// data is present."
//
// "extraSections" is the one section that isn't a single fixed block: it renders however
// many category-highlight blocks intake/site-content.json's home.extraSections array
// provides (zero, one, or many) — see doc/homepage-info-schema.md. This is the homepage's
// one open-ended extension point, for content a game genuinely needs beyond the fixed
// hero/about/featured/faq set (e.g. a keyword-dense "Characters"/"Classes"/"Items"
// highlight block per major content category) without turning the whole homepage into a
// JSON-driven module system.
export const HOME_SECTIONS = [
  "hero",
  "ads",
  "about",
  "video",
  "categories",
  "featured",
  "liveTools",
  "extraSections",
  "updates",
  "faq",
  "finalCta",
] as const;

export type HomeSection = (typeof HOME_SECTIONS)[number];

export const HOME_SECTION_ORDER: readonly HomeSection[] = [...HOME_SECTIONS];
