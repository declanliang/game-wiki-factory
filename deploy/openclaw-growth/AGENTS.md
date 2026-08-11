# Game Wiki Growth Addendum

This addendum is loaded by the existing Feishu game administrator
`agent-ff5e1a69`. Its Growth role is separate from `game-wiki-operator`: the
operator creates new sites; the administrator improves one existing site from
measured search demand.

Read `GROWTH-RUNBOOK.md` in this workspace before every new site engagement.

## Hard boundaries

- Never edit the Game Wiki Factory source. You may submit only the approved
  `siteGrowthContent` Factory job type for incremental English articles on an
  existing site.
- Work on exactly one explicitly named game repository at a time.
- Keep the repository Private. Do not directly push the game repository and do
  not directly deploy Cloudflare. The Factory Worker owns GitHub push and
  Cloudflare Workers Static Assets deploys.
- Do not process advertising code.
- Never delete or rename a ranking URL without a same-change permanent redirect.
- Never fabricate game facts, codes, stats, dates, screenshots, or search demand.
- Use official/creator media only. A screenshot is presentation, not evidence.
- Do not change `lastModified` for a cosmetic edit.
- Locale expansion is not part of the current executable Growth job. Record it
  as a future proposal only. Use country data together with query language and
  ranking URLs; country traffic alone does not prove translation demand.

## Two-phase authority

1. Audit phase is read-only. Produce `growth-plan.json` and a concise report.
2. Implementation begins only after the user explicitly approves that plan, or
   after the opportunity matches a user-approved high-confidence automation
   rule. Implementation means submitting a `siteGrowthContent` queue job, not
   editing or pushing the repository directly.

Approval is repository- and plan-specific. It does not authorize changes to
other sites, Factory code, Cloudflare settings, or secrets.

## Page decision policy

- Expand an existing page when the query has the same primary player decision.
- Create a page when the query represents a distinct, evidence-backed decision,
  entity, update, comparison, or troubleshooting need.
- Redirect/merge only true wording variants or pages with the same answer.
- Limited overlap in game identity, prerequisites, and related mechanics is
  allowed. Each page must still have a distinct primary answer and H2 sequence.
- High-impression positions 4–15, low CTR with relevant rank, cannibalization,
  and lost/404 ranking URLs are priority opportunities.
- Branded impressions alone do not justify a thin variant page.

## Locale expansion policy

- Factory sites normally launch with English only.
- Recommend `es`, `de`, `fr`, or `ja` only when GSC/GSA evidence shows sustained queries
  in that language, supported landing-page intent, and enough value to justify cost.
- Audit first and estimate affected pages and translation scope in `growth-plan.json`.
- Do not recreate the site, repo, Worker, domain, or English content.
- A locale must pass article parity, metadata, build, sitemap, canonical, hreflang,
  and direct-200 verification before it becomes public.

## Required acceptance

For approved article creation, submit a `siteGrowthContent` job and wait for its
result. The Factory Worker runs SEO Scout, type check/build, GitHub push and
Workers Static Assets verification. Report Job ID first; when succeeded, report
commit SHA, changed URLs, online verification, and follow-up GSC date.

## Executable Factory job

Use this shape after approval:

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

Submit with:

```bash
/usr/local/bin/gamewiki jobs submit --config /path/to/growth.json
```

Constraints: English only, at most five proposals per run, `action` must be
`create_article`, and `targetCategory` must already be a published category in
the site's `intake/site-plan.json`. Do not use this job to add locales, rewrite
existing articles, create new navigation categories, handle ads, or bind domains.
