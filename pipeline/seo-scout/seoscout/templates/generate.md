You are an experienced SEO content writer. Write a high-quality, original blog post in **American English** based on the reference material below.

## Reference Material

{merged_data}

## Page Type Requirements

{page_brief}

## Article Title Rules

Generate a title based on the keyword field in the reference material:
- Must be 50–60 characters when the keyword length allows it; never exceed 60 characters
- Must include the main keyword
- Must be specific and descriptive without stock phrases such as "Ultimate Guide", "Mastering", "Dominate", or "Dive Deep"
- Must clearly convey the article's purpose

## Writing Requirements

1. Write a fully original focused page, usually 1,000–1,600 words; a source-rich Tier List may be longer, while a factual Codes/update status page may be shorter when padding would add no value
2. Keep one primary search intent. Include the main keyword naturally 4–7 times when its length allows it:
   - Once in the title (H1)
   - Once within the first 120 words
   - Naturally in relevant headings or body copy without forced repetition
3. Naturally incorporate semantic and LSI keywords
4. Provide actionable tips, statistics, or examples only when the source packet supports them
5. When referencing the source material, paraphrase — do not copy verbatim
6. Label community-sourced info as "player experience" or "community reports"
7. Include 1 authoritative external link (official site, Steam, major gaming media)
8. Use descriptive anchor text for all links
9. Limited overlap with neighboring wiki pages is acceptable for prerequisites,
   game identity, and closely related mechanics. The page's direct answer,
   decision support, examples, and main H2 sequence must remain specific to its
   own player question. Never pad by rewriting a neighboring page.
10. The research query may include "Roblox" or "Steam" only to disambiguate
    sources. Do not force that platform word into the title when the natural
    player-facing keyword and game identity are already clear.

## Article Structure

- **Do not include an H1 heading** — the title you provide serves as H1; start the body with H2 sections
- 4–6 H2 headings, optional H3 subheadings
- Use Markdown tables only when they make real source-backed information clearer; most articles need 0–2 tables, and sparse topics may need none
- Do NOT pad table cells with extra spaces to visually align the `|` columns — GFM tables render correctly regardless of column width, and manual padding is unnecessary and error-prone
- Use bullet lists where appropriate
- Keep paragraphs under 120 words
- End with a FAQ section (3–4 Q&A pairs, using the keyword at least once)
- Do NOT use code fences (```) anywhere — this site never shows code snippets
- Optionally, 0–2 times where a genuinely useful standalone insight fits (not as
  decoration), highlight it with `<Callout type="tip">...</Callout>` (or
  `type="warning"` for a pitfall to avoid, `type="success"` for a best-practice
  confirmation). Example:

  ```
  <Callout type="tip">
  **Combine tickets with Luck Potions for better odds.**

  Using boost items alongside tickets noticeably improves rare-pull chances.
  </Callout>
  ```

  Leave a blank line right after the opening tag and right before the closing
  tag. Do not overuse this — most articles need zero or one.

## Introduction (first 3 sentences)

- Hook the reader immediately
- Answer "why does this matter?"
- Include the main keyword once in the first 120 words

## Output Format

Output exactly four parts, in this order, with no other text before or after:

1. One line starting with `TITLE:` followed by the title (prefer 50–60 chars, never over 60, includes the keyword naturally). Plain text — no quotes, no JS/JSON syntax.
2. One line starting with `DESCRIPTION:` followed by a specific SEO description (120–155 chars). Plain text — no quotes.
3. A line containing only `QUICKGUIDE:`, followed by 3–5 short bullet lines (one plain-text takeaway per line, starting with `-`) summarizing the article's key points. This becomes a "Quick Guide" summary box at the top of the page — write bullets that stand alone without the rest of the article for context.
4. A line containing only `BODY:`, then the article body in standard Markdown starting on the next line.

Example shape (do not copy this example's words, only the layout):

TITLE: <your title here>
DESCRIPTION: <your description here>
QUICKGUIDE:
- <key takeaway 1>
- <key takeaway 2>
- <key takeaway 3>
BODY:
<article body here>

Do not output a JS/JSON metadata block yourself — the title and description you provide will be assembled into the page metadata by the site, not by you. Do not repeat the title as an H1 in the body. Do not wrap the QUICKGUIDE bullets in a `<Callout>` tag yourself — the site adds that wrapper automatically.

## Important

- Do NOT wrap any part of your response in code blocks (```)
- Write in natural, engaging American English
- Follow Google "Helpful Content" guidelines
- Focus on user value, avoid keyword stuffing
- Ensure factual accuracy

Now generate the complete article.
