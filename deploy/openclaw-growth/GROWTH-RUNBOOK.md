# GSC growth workflow

## 1. Normalize evidence

Use the same comparison windows for Queries, Pages, Countries, Devices, Search
appearance, and Dates. Record timezone and export date. Treat anonymized GSC
queries as incomplete; page totals are authoritative for total clicks.

## 2. Build opportunity clusters

Cluster by one player decision, not by word similarity alone. For each cluster
record:

- primary query and close variants;
- clicks, impressions, CTR, average position, and trend;
- current ranking URL(s);
- intended answer and evidence URLs;
- decision: improve existing, create page, redirect/merge, monitor, or reject;
- risk: cannibalization, freshness, uncertain identity, or insufficient facts.

## 3. Prioritize

Recommended order:

1. Ranking URL is 404 or changed.
2. Position 4–15 with meaningful impressions.
3. Good position but weak CTR and mismatched title/description.
4. Two URLs divide one intent.
5. A distinct supported question has demand but no suitable page.

## 4. Propose before editing

Write `growth-plan.json` outside the repository unless the user asks to retain
it. The report must list exact URLs and distinguish shared context from the
unique answer. Ask for approval once; do not start implementation implicitly.

## 5. Implement an approved plan

Preserve URLs. Improve the first-screen answer, title/description, headings,
internal links, and official imagery only where they serve the approved intent.
Create a new page only when an existing page cannot satisfy the distinct
decision without becoming unfocused.

## 6. Verify and measure

Run local checks and production build, commit intentionally, push `main`, then
redeploy the existing Cloudflare Workers Static Assets Worker with Wrangler and
verify live output.
Choose a follow-up date at least 14 days later; compare like-for-like GSC
windows and do not declare success from same-day rank movement.

## 7. Evaluate optional locales

Treat country and language as separate signals. A German visitor using an
English query is not sufficient evidence for German translation. For `de`,
`fr`, or `ja`, record localized queries, impressions, trend, current English
landing URLs, distinct page intents, estimated page count, and translation
cost. Propose a locale expansion before editing. Once approved, translate only
the existing site's required content, add the locale to its plan, verify the
complete public locale, and push the existing repo.
