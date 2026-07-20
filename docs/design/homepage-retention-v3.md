# Homepage Retention V3

Status: implemented contract  
Scope: generated game homepages and publish handoff  
Last updated: 2026-07-20

## Business objective

The factory creates information-focused Roblox wikis whose revenue model depends on ad CPM. Ads are outside this implementation, but the homepage must help users understand the game, find the next useful page, and stay long enough to consume more information.

The site may publish cautious summaries when perfect verification would be uneconomical. It must still reject obviously wrong, clearly unrelated, or cross-game information. Layout depth never justifies fabricated facts or empty categories.

## Information ownership

- Basic Info owns game identity, homepage facts, quick facts, FAQ, and guide-section copy.
- `game-profile.json` defines the category boundary; `site-plan.json` is the only published category source.
- Existing article output supplies article and category links. The template never invents destinations.
- Basic Info's verified trailer wins. If it is absent, the orchestrator may select one video from the already-cached Guide Search YouTube response.
- A fallback video must be long-form (2–60 minutes), explicitly identify Roblox, and contain the complete normalized game name in its title. Shorts, live streams, partial-name ambiguity, and unrelated high-view videos are rejected.
- Selecting a third-party video fills only `YOUTUBE_VIDEO_ID`; it never fills `YOUTUBE_CHANNEL_URL` or labels that channel as official. Selection provenance is stored in `.gamewiki/planning/featured-video.json`.

## Homepage composition

Default order:

1. Hero, CTAs, and four aligned stat cards.
2. Click-to-load YouTube gameplay video when available.
3. Optional advertising slot.
4. About copy and Quick Facts in a constrained two-column layout.
5. Two to four evidence-backed field-guide sections.
6. Published categories, centered for one or many cards.
7. Featured article links and optional category highlights.
8. Constrained Latest Updates list.
9. FAQ and final CTA.

Width hierarchy:

- Page shell: at most 90rem.
- Wide editorial sections: 72rem.
- Video and card modules: 64rem.
- Updates and FAQ: 56rem.
- Long copy inside a column: roughly 42rem.

The homepage should not repeat one full-width bordered panel for every section. Numbered guide items use independent cards and icon-like `01`, `02`, `03` badges without horizontal separators.

## Retention and internal linking

- Every published category appears as a real link only when it contains an article.
- Guide-section items link only to categories declared `published` by site-plan.
- Featured and Latest Updates link to real article routes generated from content metadata.
- A single category or a single update is centered and remains compact instead of stretching across the viewport.
- Video is click-to-load and uses the privacy-enhanced YouTube embed domain; there is no autoplay until the visitor explicitly starts playback.

## Publishing handoff

- GitHub repositories are Private-only and visibility is verified after creation and before update pushes.
- Vercel automation imports/connects the project but never sets environment variables.
- The publish receipt remains `awaiting_domain_configuration` until the owner binds the final domain, sets `NEXT_PUBLIC_SITE_URL`, deploys, and runs `npm run verify:deploy`.

## Acceptance cases

Validate at least:

- a long two-line stat value next to one-line values;
- one, two, and four category cards;
- one and four latest articles;
- a verified Basic Info video, a selected cached fallback video, and no acceptable video;
- desktop and mobile layouts;
- all six locales, TypeScript, production build, sitemap, canonical, OG, and hreflang.
