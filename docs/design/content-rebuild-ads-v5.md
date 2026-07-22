# Content Expansion, Rebuild, and Ads V5

## Outcome

The factory produces information-rich Roblox/Steam guide sites without turning page count into a quota. It also treats old sites as fresh builds and accepts unmodified Adsterra JSON as a separate recoverable background task.

## Content opportunity policy

Guide Search has two discovery layers:

1. Demand evidence: Google Suggest main+a–z, DataForSEO, manual inputs, and repeated same-game YouTube themes.
2. Knowledge opportunities: web research for concrete systems, entities, codes, updates, progression, currencies, upgrades, modes, maps, bosses, items, and quests.

An exact autocomplete keyword is not required for the second layer. A standalone opportunity still needs at least one official/creator URL or two distinct supporting URLs, confidence at least 0.72, and a category allowed by Basic Info. The final editorial gate removes unrelated meanings, unsupported generic pages, one-off entertainment topics, and duplicates. Minor factual uncertainty is acceptable in later article writing; unsupported identity and completely unrelated topics are not.

`content-opportunity-report.json` makes the funnel auditable: source response counts, discovered candidates, researched opportunities, admitted candidates, selected pages, selected categories/page types/sources, entity coverage, and rejection counts.

## Old-site rebuild

There is one site pipeline. `operation: rebuild` archives the old local workspace, runs all current collection/generation stages from empty state, restores any nonstandard repo/project names from the old publish receipt, creates a remote backup tag, and replaces `main`. It never merges historical template code. Vercel project, custom domain, and existing unrelated environment variables remain attached.

## Adsterra import contract

The seven exact titles are mapped deterministically:

| Adsterra title | Vercel variable | Site placement |
|---|---|---|
| Native Banner | `AD_NATIVE_BANNER_B64` | Hero/card flows |
| Banner 468x60 | `AD_BANNER_468X60_B64` | Desktop footer |
| Banner 300x250 | `AD_BANNER_300X250_B64` | Mobile/content |
| Banner 160x300 | `AD_SIDEBAR_160X300_B64` | Right article rail |
| Banner 160x600 | `AD_SIDEBAR_160X600_B64` | Left/sidebar rail |
| Banner 320x50 | `AD_MOBILE_320X50_B64` | Global top sticky |
| Banner 728x90 | `AD_BANNER_728X90_B64` | Desktop content/footer |

The importer rejects unknown, missing, duplicate, or misspelled titles. Banner width/height and `atOptions.key` must match the external invoke path; Native container ID must match its invoke path. The supplied domain must already belong to the resolved Vercel project. All seven values are upserted only after the entire JSON passes validation, then one production deployment is created and each isolated `/api/ads/<format>` response is hash-verified. Creative fill is not treated as a deployment requirement because Adsterra may synchronize later.
