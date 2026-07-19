// Shared by apply-content.mjs (fills en.json from intake/site-content.json) and
// apply-locales.mjs (fills src/locales/<locale>.json from intake/site-content.<locale>.json)
// — both are the same "merge a structured site/home payload onto a locale object" operation,
// just applied to a different target file. Kept in one place so the one subtlety in it (arrays
// like extraSections must be replaced wholesale, never object-spread) can't drift out of sync
// between the two callers the way it would if each reimplemented this merge separately.

// If the whole game name was typed in lowercase, title-case it for display (it gets used
// verbatim in headings/titles/copy) — but leave any name with intentional casing (acronyms,
// stylized capitals like "inFAMOUS") untouched.
export function resolveGameName(env) {
  const raw = env.GAME_NAME;
  if (!raw) return raw;
  return raw === raw.toLowerCase() ? raw.replace(/\b\w/g, (c) => c.toUpperCase()) : raw;
}

export function tokenValues(env) {
  return {
    __GAME_NAME__: resolveGameName(env),
    __OFFICIAL_GAME_URL__: env.OFFICIAL_GAME_URL,
    __YEAR__: String(new Date().getFullYear()),
  };
}

// Mutates `target` (an en.json-shaped object, or a locale file's partial equivalent) by
// merging a structured { site, home } payload onto it. `target.site`/`target.home`/
// `target.footer` are created as {} if the target doesn't already have them (true for a bare
// locale file that only carries template-baseline nav/shared/footer strings, unlike en.json
// which always has the full skeleton from the template).
export function applyStructuredContent(target, structured) {
  target.site = { ...(target.site ?? {}), ...(structured.site ?? {}) };
  target.home = target.home ?? {};
  if (structured.home) {
    for (const key of Object.keys(structured.home)) {
      if (key === "liveTools" || key === "extraSections") continue; // arrays/all-or-nothing, handled below
      target.home[key] = { ...(target.home[key] ?? {}), ...structured.home[key] };
    }
  }

  // liveTools/extraSections are all-or-nothing: only present in the output if the structured
  // file actually provided them — the generic per-key merge above would silently corrupt
  // extraSections (an array) by object-spreading it into a plain numeric-keyed object, so
  // it's excluded there and replaced wholesale here instead.
  if (structured.home?.liveTools) target.home.liveTools = structured.home.liveTools;
  else delete target.home.liveTools;

  if (Array.isArray(structured.home?.extraSections) && structured.home.extraSections.length > 0) {
    target.home.extraSections = structured.home.extraSections;
  } else {
    delete target.home.extraSections;
  }

  target.footer = target.footer ?? {};
  if (target.site.description !== undefined) target.footer.description = target.site.description;
}

// Replaces __GAME_NAME__/__OFFICIAL_GAME_URL__/__YEAR__ tokens anywhere in a value tree —
// used on template-baseline UI strings (footer.about etc.) that reference the game name but
// are otherwise identical across every game built on this template.
export function substituteTokens(value, values) {
  if (typeof value === "string") {
    let out = value;
    for (const [token, replacement] of Object.entries(values)) {
      if (replacement !== undefined) out = out.split(token).join(replacement);
    }
    return out;
  }
  if (Array.isArray(value)) return value.map((v) => substituteTokens(v, values));
  if (value && typeof value === "object") {
    const out = {};
    for (const k of Object.keys(value)) out[k] = substituteTokens(value[k], values);
    return out;
  }
  return value;
}
