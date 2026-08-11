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

For approved English article creation, convert each accepted opportunity into a
Factory `siteGrowthContent` proposal. Do not edit the repository directly.

```json
{
  "schemaVersion": 1,
  "taskType": "siteGrowthContent",
  "slug": "existing-site-slug",
  "siteUrl": "https://existing-site.example",
  "githubRepo": "declanliang/existing-site-slug",
  "source": "agent-ff5e1a69:gsc",
  "publish": true,
  "proposals": [
    {
      "action": "create_article",
      "keyword": "Existing Site specific guide",
      "targetCategory": "guide",
      "intent": "The concrete player question this page answers.",
      "reason": "GSC-backed opportunity summary.",
      "evidence": {"impressions28d": 100, "avgPosition28d": 12.5}
    }
  ]
}
```

Submit it to the background queue:

```bash
/usr/local/bin/gamewiki jobs submit --config /path/to/growth.json
```

The current executable Growth job is intentionally narrow: English only, at
most five new-article proposals per run, and every `targetCategory` must already
be a published category in `intake/site-plan.json`. If the opportunity needs a
new navigation category, locale, rewrite, redirect, ad change, or domain work,
stop and produce a separate proposal instead of forcing it into this task.

## 6. Verify and measure

Watch the submitted Job ID. The Factory Worker runs SEO Scout, connects the MDX
article, refreshes Latest Articles/homepage links, commits/pushes the Private
repo, deploys the existing Cloudflare Workers Static Assets Worker, and verifies
live output.

Only report success after the job is `succeeded` and its result contains changed
URLs plus online verification. If the job fails because evidence is too thin or
QA rejects the article, do not invent filler; report the rejected opportunity.
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
