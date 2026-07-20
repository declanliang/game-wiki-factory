# Game Wiki Factory Production Automation V2

Status: implementation contract
Scope owner: `game-wiki-factory`
Last updated: 2026-07-20

## 1. Objective

Upgrade the existing single-game pipeline into an unattended production factory that can:

1. Produce a deeper, evidence-backed homepage without allowing downstream article generation to invent homepage facts or categories.
2. Run two or three games concurrently while enforcing shared API and local-resource limits.
3. Expose machine-readable status, resumable checkpoints, and complete per-game logs so a human or AI can diagnose a run without retaining conversation context.
4. Publish a completed game as its own GitHub repository and Vercel project through one idempotent command.
5. Offer the same generate-and-publish path from a manually dispatched GitHub Actions workflow.

The implementation must preserve the existing per-game layout:

```text
Games/<slug>/
├─ package.json
├─ intake/                 committed deployment input
└─ .gamewiki/              ignored local state, cache, logs, receipts
```

## 2. Explicit exclusion

The proposed “one keyword, one article” Topic Contract is **not part of this implementation**. Do not change:

- Guide Search keyword output semantics;
- SEO Scout keyword-to-article mapping;
- article generation prompt keyword-density rules;
- topic/cannibalization QA.

That work remains a separate future migration and must not be mixed into the concurrency, homepage, or publishing changes.

## 3. Non-negotiable invariants

- Factory source is clean and contains no real-game output.
- Real games are siblings of the factory and never nested in it.
- Secrets are read from process environment or ignored `.env` files; they are never copied, printed, committed, or written to publish receipts.
- Fixed locale order is `en/es/de/fr/ja/ko`.
- Basic Info facts remain the only source of homepage facts.
- `game-profile.json` remains the category boundary; `site-plan.json` remains the sole published category/language declaration.
- SEO Scout output may provide existing article links for homepage navigation, but may not create homepage facts or categories.
- A checkpoint is skipped only after validation.
- Every external command has a dedicated log and every failed run updates a manifest with a traceback.
- Concurrent games never share a mutable project directory, verification port, or generated content tree.

## 4. Homepage depth design

### 4.1 Information model

Extend the Basic Info homepage research output with an optional `home.guideSections` array. It is generated from validated Basic Info facts/evidence and converted into template intake by `template_contract.py`.

Each section has:

```json
{
  "id": "core-gameplay",
  "eyebrow": "Gameplay",
  "title": "How the game works",
  "description": "A concise section introduction.",
  "items": [
    {
      "title": "Build your first team",
      "description": "Evidence-backed explanation without unsupported numbers.",
      "category": "guide"
    }
  ]
}
```

Allowed section IDs:

- `core-gameplay`
- `beginner-path`
- `progression`
- `game-modes`
- `key-systems`
- `current-highlights`

Rules:

- 2–4 sections when evidence supports them.
- 2–6 items per section.
- No invented counts, rewards, units, maps, bosses, codes, dates, or mechanics.
- `category` is optional and, when present, must be a category candidate from the Basic Info game profile.
- Basic Info does not create article slugs or hrefs.
- Localized homepage files keep identical IDs, item order, and category values; only human-facing strings are translated.

### 4.2 Intake and site-plan reconciliation

The final intake field is `home.guideSections`. During intake preparation:

1. Preserve Basic Info section copy and ordering.
2. Drop any optional `category` that is not published in `site-plan.json`.
3. Resolve an existing category href (`/<category>`) for published categories.
4. Never scan `content/en` to infer a category.

This keeps source ownership explicit:

```text
Basic Info facts/evidence → section copy
game-profile/site-plan    → allowed and published categories
template assembler        → deterministic category links
```

### 4.3 Rendering

Add a `guideSections` slot between About Game and Featured Guides. The design direction is an editorial field guide:

- dense, scannable information rather than decorative cards;
- visible section numbering and strong hierarchy;
- asymmetric desktop composition with a compact mobile stack;
- existing site palette and typography remain authoritative;
- semantic headings, keyboard-safe links, and no hover-only information;
- no new runtime dependency.

Homepage acceptance:

- Existing sites without `guideSections` render unchanged.
- New evidence-rich games render at least two guide sections.
- Intake/locales remain structurally identical across six languages.
- No dead category link is emitted.
- Homepage JSON-LD, canonical, sitemap, and performance behavior remain valid.

## 5. Concurrent execution architecture

### 5.1 CLI

Retain the single-game command:

```powershell
python gamewiki.py "Game Name"
```

Add a multi-game command:

```powershell
python gamewiki.py run-many "Game A" "Game B" --jobs 2
python gamewiki.py run-many --games-file games.txt --jobs 3
```

Add observability commands:

```powershell
python gamewiki.py status
python gamewiki.py status <slug>
python gamewiki.py logs <slug> --tail 100
python gamewiki.py resume <slug>
```

`resume` is an alias for the normal checkpoint-validating single-game run. It never implies refresh, recluster, or overwrite.

### 5.2 Supervisor

The multi-game supervisor owns:

- the game job semaphore (`--jobs`);
- a shared API permit broker;
- child process lifecycle and exit codes;
- aggregate run manifest and summary;
- per-game environment containing a broker endpoint/token and an automatically selected verification port.

Each game remains a separate process so a crash, Python module cache, or working-directory change cannot corrupt another game.

Aggregate state:

```text
factory/.gamewiki/runs/<run-id>/
├─ manifest.json
├─ events.jsonl
└─ games/<slug>.log
```

No API response bodies or secrets are written to aggregate logs.

### 5.3 API permit broker

All concurrent local game processes request permits from one localhost-only broker. Initial resource classes:

| Resource | Default global limit | Notes |
|---|---:|---|
| `llm` | 10 | bounded again per key slot |
| `dataforseo` | 3 | matches current YouTube search workers |
| `serper` | 5 | matches current web search concurrency |
| `jina` | 20 | matches current extraction concurrency |
| `build` | 1 | prevents simultaneous memory-heavy Next builds |

The broker is optional for a single-game run. Without broker environment variables, existing local semaphores remain the fallback.

### 5.4 Multi-key LLM scheduling

Existing `LLM_API_KEY_1..N` support is retained and hardened:

- discover all non-empty numbered slots without stopping at the first missing number;
- never log key material; identify only `key_slot`;
- per-key concurrency is configurable (`LLM_CONCURRENCY_PER_KEY`, default 3);
- global concurrency is `min(configured global limit, active keys × per-key limit)`;
- round-robin assignment only considers keys with an available slot;
- 402/403 quota errors disable one key for the run;
- 429 reduces pressure on the affected key;
- common 5xx/52x errors use bounded exponential backoff and may move the retry to another key;
- completed outputs are persisted immediately.

Multiple keys improve throughput only when their provider limits are independent. The scheduler must not assume that three keys equal three times the capacity.

### 5.5 Queue instead of batch barriers

Generation, QA, and translation use a continuous worker queue:

- at most the configured concurrency is active;
- a completed task immediately frees capacity for the next task;
- one slow request no longer blocks all other items in a fixed batch;
- results retain input ordering where reports require it;
- every valid result is written before the next potentially failing operation;
- retry and repair tasks re-enter the queue with bounded priority.

### 5.6 Port and build isolation

- Verification accepts `GAMEWIKI_VERIFY_PORT`; `0` requests an available ephemeral port.
- Concurrent runs never use a hard-coded port 3100.
- Build work requires the broker `build` permit.
- npm cache may be shared, while `node_modules`, `.next`, and intake remain per game.

## 6. Status and logging contract

Every stage emits a structured event:

```json
{
  "timestamp": "...",
  "runId": "...",
  "game": "...",
  "slug": "...",
  "stage": "translate",
  "event": "progress",
  "completed": 73,
  "total": 200,
  "keySlot": 2
}
```

Required summaries:

- stage start/end/duration;
- cached/generated/failed counts;
- API request count, retry count, HTTP error classes, token count where returned;
- article counts by locale;
- current command and checkpoint path;
- publish repo/project/deployment URLs without tokens.

`status` reads manifests and events only. It never calls an external API.

## 7. GitHub and Vercel publishing

### 7.1 CLI

```powershell
python gamewiki.py publish <slug>
python gamewiki.py "Game Name" --publish
python gamewiki.py run-many --games-file games.txt --jobs 2 --publish
```

Publishing is allowed only when the project manifest is complete and local production verification has passed.

### 7.2 Secrets and configuration

```text
FACTORY_GITHUB_TOKEN       token/App user token capable of creating repositories
GITHUB_OWNER               destination user or organization
GITHUB_REPO_VISIBILITY     public|private (default private)
VERCEL_TOKEN               Vercel access token
VERCEL_TEAM_ID             optional team ID
VERCEL_GIT_PROVIDER        github
```

`GITHUB_TOKEN` supplied to an ordinary Factory workflow is not assumed to have cross-repository creation rights.

### 7.3 Idempotent state machine

`publish` performs:

1. Validate manifest, intake, clean secret scan, production build receipt.
2. Produce the commit allowlist; exclude `.gamewiki`, `.env*`, logs, caches, `node_modules`, `.next`.
3. Look up `<owner>/<slug>`.
4. Create it when absent; otherwise verify ownership and reuse it.
5. Initialize/update local Git, commit only when content changed, and push `main`.
6. Look up a Vercel project named `<slug>`.
7. Create it when absent with `gitRepository.type=github`, repository full name, Next.js framework, and empty root directory.
8. Set `NEXT_PUBLIC_SITE_URL` to the configured custom origin or the stable production `https://<slug>.vercel.app` origin.
9. Trigger/wait for production deployment.
10. Run remote `verify:deploy` against the actual production URL.
11. Write `.gamewiki/publish.json` with non-secret IDs, URLs, commit SHA, status, and timestamps.

Re-running publish updates the same repository and Vercel project. Name collisions owned by another account fail safely.

### 7.4 GitHub Actions

Add `.github/workflows/generate-and-publish.yml` to the Factory repository:

- trigger: `workflow_dispatch`;
- inputs: JSON game-name array, `max_parallel`, `publish`, visibility, optional site-origin map;
- matrix job with bounded `max-parallel`;
- tests before paid generation;
- generate, build, publish, verify;
- upload manifest and sanitized logs on both success and failure;
- use a protected `production` environment for publishing secrets;
- never expose publishing secrets to pull-request workflows.

Generated game repositories receive a small CI workflow for deterministic intake/type/build validation. Vercel Git integration remains responsible for deployment on later pushes; do not duplicate every push deployment in GitHub Actions.

## 8. Failure and resume behavior

- A failed game does not cancel unrelated games unless `--fail-fast` is explicitly set.
- The aggregate command returns non-zero when any game fails and prints a per-game summary.
- Retry the aggregate command or `resume <slug>`; validated checkpoints are reused.
- Publishing never begins for a failed/incomplete game.
- If GitHub succeeds and Vercel fails, the receipt records `github=complete`, `vercel=failed`; resume starts from Vercel.
- If deployment succeeds and verification fails, do not create another project; repair and redeploy the same project.

## 9. Security

- Redact Authorization headers, tokens, `.env` values, and signed URLs from logs.
- Never run paid/publish workflows from untrusted PR code.
- Pin third-party Actions to immutable commit SHAs where practical.
- Use minimum GitHub/Vercel permissions.
- Validate repo owner/name, project name, output root, and all destructive copy/remove targets.
- Bind the local permit broker to loopback and require a per-run random token.

## 10. Test plan

### Unit and contract tests

- Homepage schema accepts/validates `guideSections` and rejects unknown IDs or unapproved categories.
- Six locale homepage trees remain identical.
- Existing homepage intake without `guideSections` remains valid.
- Multi-key discovery handles missing numeric slots and duplicates.
- Per-key/global concurrency never exceeds configuration.
- Quota/error behavior disables only the affected key.
- Worker queue persists partial success and avoids batch barriers.
- Dynamic verification ports do not collide.
- Publish state machine is idempotent with mocked GitHub/Vercel APIs.
- Secret scan blocks unsafe publication.

### Repository suites

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -s pipeline/basic-info/tests -v
$env:PYTHONPATH=(Resolve-Path pipeline/guide-search).Path
python -m unittest discover -s pipeline/guide-search/tests -v
node --check template/scripts/*.mjs
cd template
npx tsc --noEmit
```

### Required real concurrent acceptance

Run without refresh/recluster/overwrite:

```powershell
python gamewiki.py run-many "My Giant Sandwich" "Guess the character color" --jobs 2
```

For both games verify:

- independent sibling project directories;
- no fixed-port, file, log, cache, or manifest collision;
- Basic Info produces at least two evidence-backed `guideSections` when source evidence permits;
- category boundary and site plan remain valid;
- six locale article trees match;
- intake validation, TypeScript, production build, sitemap direct-200, canonical, OG, and hreflang pass;
- aggregate status reports both games and durations;
- a second zero-cost resume reuses valid checkpoints.

Publishing automation is verified with mocked APIs unless explicit live GitHub/Vercel credentials and authorization are available. Do not create live repositories or Vercel projects merely to test code without that authorization.

## 11. Rollout sequence

1. Land this design and update operator documentation.
2. Implement homepage schema, Basic Info output, localization, template rendering, and compatibility tests.
3. Implement supervisor, permit broker, dynamic ports, queue scheduling, status/logs/resume.
4. Implement publish state machine and mocked integration tests.
5. Add Factory and generated-site workflows.
6. Run all repository suites.
7. Run the required two-game concurrent acceptance.
8. Fix generic issues and resume without paid overwrite.
9. Run idempotence checks and publish Factory changes to `main`.
