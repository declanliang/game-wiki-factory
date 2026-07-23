# Content Depth V4：从少量长文到可导航的游戏知识站

Status: approved for implementation  
Scope: Basic Info category boundary, Guide Search discovery, site plan, SEO Scout generation, homepage composition  
Out of scope: calculators, planners, team builders, ad integration, arbitrary page-count targets  
Last updated: 2026-07-21

## 1. Business goal

The factory must turn a Roblox or Steam game into an information-rich fan wiki rather than a small collection of long generic guides. A useful fact may be published with an explicit community/reported qualifier when perfect verification is uneconomical, but obviously wrong, cross-game, or unsupported information remains forbidden.

The desired content model is:

- one focused player need or named game entity per page;
- several related pages connected through category hubs, homepage spotlights, and related-content links;
- enough homepage depth to let visitors choose their next task without reading one monolithic article;
- no synthetic pages created only to hit a numeric quota.

## 2. Competitive baseline

The implementation should first close the useful gaps observed on Anime Squadron, Noob Incremental, and Storage Hunters Open World:

- game-specific hero artwork and visual identity;
- Codes, Tier List, Updates, and named character/unit/entity coverage;
- category hubs that expose multiple focused pages;
- homepage previews for high-value categories;
- substantially more useful internal entry points.

The implementation must not copy their defects: cross-domain canonical URLs, nonexistent sitemap hosts, oversized research-log banners, unsupported calculators, thin status pages, or near-duplicate keyword pages.

## 3. Content types in this release

All published output remains localized MDX and uses the existing category/detail routes.

### 3.1 Codes

Create at most one canonical Codes page per game. It may be a status page when reliable current sources report no active codes, but it must still answer redemption availability, verification date, where codes are normally announced, and common troubleshooting. Never invent a code or reward.

### 3.2 Tier List

Create a Tier List page only when the game has rankable units, characters, weapons, traits, mutations, classes, or another clearly comparable set. Rankings must explain their basis and mark community judgment as such. Do not create a tier list from a game genre label alone.

### 3.3 Updates

Use the existing Updates category as an update center. Each sufficiently distinct version, event, or major change may become a focused MDX page when dated source evidence exists. Generic “latest update” and a named version should merge when they satisfy the same intent.

### 3.4 Entity pages

Named characters, units, bosses, modes, items, resources, maps, quests, traits, and mechanics may become focused pages when they are clearly part of the game and meet the evidence gate below. These pages should answer what the entity is, how players encounter or obtain it, why it matters, and the next related decision.

### 3.5 Existing guide pages

Beginner, progression, mechanics, economy, bosses, and other existing guides remain supported. Broad guides should link to focused pages instead of repeating every entity in full.

## 4. Evidence-backed coverage discovery

Google Suggest main+a-z, DataForSEO, and YouTube candidates remain inputs. Guide Search's existing web-research context stage is expanded to return `page_opportunities` as an audited discovery artifact. The context model receives a compact list of deduplicated YouTube titles and URLs, not transcripts; repeated named entities can therefore become focused pages without treating a single entertainment video as proof.

Each opportunity must contain:

- proposed search-facing topic;
- page type and normalized category;
- optional entity name/type;
- short player intent;
- confidence;
- evidence URLs and evidence source types;
- whether any evidence is first-party or official.

An opportunity may enter clustering only when:

- confidence is at least 0.72; and
- it has either one official/creator-owned source or at least two distinct supporting URLs; and
- it is not a community-navigation topic such as Discord, Reddit, Trello, logo, or game link; and
- it names a specific same-game player need or entity; and
- its category is allowed by the Basic Info game profile.

For roster or collection games, a named unit/item/boss may become its own opportunity when at least two distinct videos support the same entity, or one official/creator source does. An umbrella Units page does not replace supported individual entity pages.

The web-research stage may propose evidence-backed coverage topics. The later clustering stage still cannot invent additional topics; it may only keep, merge, recategorize within the profile, or drop the combined candidate set.

Every admitted research opportunity is recorded in `candidates.json` and `keywords.json` with provenance. Rejected opportunities retain a reason so future AI operators can distinguish “not found” from “found but below the evidence threshold.”

## 5. Category ownership

Basic Info remains the sole owner of the semantic boundary. Its game profile is expanded to understand at least:

- `tier-list`
- `characters`
- `codes`
- `updates`
- `modes`
- `items`
- `quests`
- existing guide/progression/mechanics/economy/bosses/etc.

Tier List is allowed only when Basic Info contains rankable entity evidence. Characters is allowed for character/unit/hero/class evidence. Codes is allowed for a redeem/code system, sourced code records, or as a Roblox platform capability candidate. The profile may expose up to sixteen allowed candidates so later research does not lose a real category to an early slot cap; the final site plan still publishes at most eight categories.

`site-plan.json` remains the only source of truth for published categories, order, localized labels/descriptions, topic records, and delivery status.

## 6. SEO Scout page-specific generation

`seo-keywords.json` carries a topic specification for each keyword. Search and collection remain backward compatible with the existing string keyword list. Generation receives a page-type brief:

- Codes: verified/status table when supported, redemption, expiry/status labels, troubleshooting, source cautions.
- Tier List: ranking basis, tiers or comparison groups only when supported, alternatives, update sensitivity.
- Updates: version/date scope, confirmed changes, affected systems, player actions, source/status note.
- Entity: identity, acquisition/location, role or use, related systems, cautions, next related pages.
- Guide: focused how-to answer without absorbing unrelated entity topics.

All page types retain the existing metadata, topic QA, translation completeness, and five-language tree requirements. The generator must not manufacture tables, values, codes, dates, or rankings when the collected source packet does not support them.

## 7. Homepage and internal linking

The homepage uses the processed game hero image as an optimized background with a readable overlay and the existing gradient as a fallback. It does not copy low-resolution stretching or oversized update banners.

After content materialization, the deterministic homepage script creates localized category spotlight sections from published MDX:

- one section for each high-value published category with at least two pages;
- up to four article links per section;
- localized heading and description from site plan;
- a localized category-hub link;
- no links to missing or unfulfilled content.

General Featured and Latest Updates remain, but category spotlights expose the deeper information architecture. Article related links continue to prefer the same category before filling from other categories.

## 8. Checkpoint and cost policy

Existing raw search, context, cluster, article, QA, and translation checkpoints remain reusable only when their contract fingerprints are valid. The context and cluster policy versions must change because page-opportunity discovery changes their semantics. Normal failure recovery still reruns the same command without refresh/recluster/overwrite.

When upgrading an already generated game, old articles are not regenerated merely to adopt the new template. A full V4 content test intentionally uses new game projects so all new contracts execute from clean checkpoints.

## 9. Acceptance criteria

### Offline

- root Python tests pass;
- Basic Info tests pass;
- Guide Search tests pass, including evidence admission/rejection and Tier List/category normalization;
- template script syntax, TypeScript, intake validation, and production build pass;
- legacy string-only keyword files remain accepted.

### End to end

Use two of the three competitive-reference games. Default test pair:

1. Anime Squadron — exercises Codes, Tier List, characters/units, updates, and guide coverage.
2. Storage Hunters Open World — exercises items/resources, mutations or mechanics, quests, economy, updates, and guide coverage.

For each project verify:

- official Roblox identity is correct;
- no obviously unrelated candidate survives;
- evidence-backed focused pages materially outnumber the previous 3–5-page baseline when sources support them;
- Codes/Tier List/Updates/entity categories appear only when evidence supports them;
- at least four published categories when the source set supports four;
- homepage includes the real hero image, category spotlights, video when available, and real internal links;
- six locale trees are identical;
- intake, TypeScript, production build, sitemap, canonical, OG, and hreflang checks pass;
- no calculator/tool page is generated;
- final comparison records remaining differences from the reference sites without lowering factual relevance gates.

## 10. Documentation handoff

After implementation update the root README, architecture, runbook, AI handoff, and affected module AGENTS files. A new operator should understand that Google keyword evidence and evidence-backed knowledge opportunities are two complementary discovery channels, and that neither authorizes unrelated or quota-driven pages.
