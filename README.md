# Game Wiki Automation Projects

This repository groups the tools used to research, prepare, and build game Wiki sites. Each project lives in its own directory and keeps its own setup instructions.

## Projects

| Directory | Purpose |
|---|---|
| [`auto-basic-info/`](auto-basic-info/) | Research a Roblox game from its name and generate validated homepage configuration, localized content, Hero imagery, and favicon assets for the shared Wiki template. |
| [`keyword-research/`](keyword-research/) | Collect Google Suggest, DataForSEO, Similarweb, Google Trends, and YouTube signals, then produce an audited `keywords.json` for SEO content planning. |
| [`seoscout/`](seoscout/) | Take an audited `keywords.json` the rest of the way: search YouTube + Google, collect transcripts/web content, generate SEO MDX articles with an LLM (Quick Guide box + inline callouts included), review them for topic relevance, and translate into other languages. |

Start with the README inside the project you want to use. Secrets, API caches, and generated game output are intentionally excluded from Git.
