// Cloudflare Pages Function — replaces src/app/api/ads/[format]/route.ts,
// which cannot exist under `output: "export"` (no dynamic Next.js server here).
// Keeps the same contract: ad snippets stay server-only (Pages env vars),
// never shipped in the client bundle, and never cached (no-store).

const AD_FORMATS = ["nativeBanner", "banner728x90", "banner300x250", "banner468x60", "sidebar160x600", "sidebar160x300", "mobile320x50"] as const;
type AdFormat = (typeof AD_FORMATS)[number];

function isAdFormat(value: string): value is AdFormat {
  return (AD_FORMATS as readonly string[]).includes(value);
}

function decodeSnippet(encoded: string | undefined): string | undefined {
  if (!encoded?.trim()) return undefined;
  try {
    return atob(encoded.trim()).trim() || undefined;
  } catch {
    return undefined;
  }
}

function rawSnippet(value: string | undefined): string | undefined {
  return value?.trim() || undefined;
}

type Env = Record<string, string | undefined>;

// Matches the env var names documented in .env.example exactly — do not derive
// these programmatically, the format-name-to-ENV_VAR casing isn't a clean regex
// (e.g. banner728x90 -> BANNER_728X90, not BANNER_728X_90).
const ENV_KEY: Record<AdFormat, string> = {
  nativeBanner: "NATIVE_BANNER",
  banner728x90: "BANNER_728X90",
  banner300x250: "BANNER_300X250",
  banner468x60: "BANNER_468X60",
  sidebar160x600: "SIDEBAR_160X600",
  sidebar160x300: "SIDEBAR_160X300",
  mobile320x50: "MOBILE_320X50",
};

function getAdSnippet(format: AdFormat, env: Env): string | undefined {
  const key = ENV_KEY[format];
  const b64 = env[`AD_${key}_B64`];
  const plain = env[`AD_${key}`];
  const pub = env[`NEXT_PUBLIC_AD_${key}`];
  return decodeSnippet(b64) ?? rawSnippet(plain) ?? rawSnippet(pub);
}

export const onRequestGet: PagesFunction<Env> = async (context) => {
  const format = context.params.format as string;
  if (!isAdFormat(format)) return new Response("Not found", { status: 404 });

  const snippet = getAdSnippet(format, context.env);
  if (!snippet) return new Response("Not found", { status: 404 });

  const native = format === "nativeBanner";
  const normalizedSnippet = snippet.replace(/(<script\b[^>]*\bsrc=["'])\/\//gi, "$1https://");
  const html = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>html,body{margin:0;width:100%;height:100%;overflow:hidden;background:transparent}body{display:${native ? "block" : "flex"};align-items:center;justify-content:center}body>div{max-width:100%}</style></head><body><!--gamewiki-ad-start-->${normalizedSnippet}<!--gamewiki-ad-end--></body></html>`;

  return new Response(html, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "private, no-store",
      "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline' https: http:; style-src 'unsafe-inline'; img-src https: http: data:; frame-src https: http:; connect-src https: http:; font-src https: data:; base-uri 'none'; form-action https: http:; frame-ancestors 'self'",
      "Referrer-Policy": "strict-origin-when-cross-origin",
      "X-Content-Type-Options": "nosniff",
    },
  });
};
