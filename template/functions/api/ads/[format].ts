// Cloudflare Pages Function — replaces src/app/api/ads/[format]/route.ts,
// which cannot exist under `output: "export"` (no dynamic Next.js server here).
// Keeps the same contract: ad snippets stay server-only (Pages env vars),
// never shipped in the client bundle, and never cached (no-store).

const AD_FORMATS = ["nativeBanner", "nativeBannerMobile", "banner728x90", "banner300x250", "banner468x60", "sidebar160x600", "sidebar160x300", "mobile320x50"] as const;
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

type Env = Record<string, string | undefined>;

const ENV_KEY: Record<AdFormat, string> = {
  nativeBanner: "AD_NATIVE_BANNER_B64",
  nativeBannerMobile: "AD_NATIVE_BANNER_MOBILE_B64",
  banner728x90: "AD_BANNER_728X90_B64",
  banner300x250: "AD_BANNER_300X250_B64",
  banner468x60: "AD_BANNER_468X60_B64",
  sidebar160x600: "AD_SIDEBAR_160X600_B64",
  sidebar160x300: "AD_SIDEBAR_160X300_B64",
  mobile320x50: "AD_MOBILE_320X50_B64",
};

function getAdSnippet(format: AdFormat, env: Env): string | undefined {
  return decodeSnippet(env[ENV_KEY[format]]);
}

export const onRequestGet: PagesFunction<Env> = async (context) => {
  const format = context.params.format as string;
  if (!isAdFormat(format)) return new Response("Not found", { status: 404 });

  const snippet = getAdSnippet(format, context.env);
  if (!snippet) return new Response("Not found", { status: 404 });

  const native = format === "nativeBanner" || format === "nativeBannerMobile";
  const normalizedSnippet = snippet.replace(/(<script\b[^>]*\bsrc=["'])\/\//gi, "$1https://");
  const html = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>html,body{margin:0;width:100%;height:100%;overflow:hidden;background:transparent}body{display:${native ? "block" : "flex"};align-items:center;justify-content:center}body>div{max-width:100%}</style></head><body><!--gamewiki-ad-start-->${normalizedSnippet}<!--gamewiki-ad-end--></body></html>`;

  return new Response(html, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "private, no-store, no-cache, max-age=0, must-revalidate",
      "CDN-Cache-Control": "no-store",
      "Cloudflare-CDN-Cache-Control": "no-store",
      "Vary": "Accept",
      "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline' https: http:; style-src 'unsafe-inline'; img-src https: http: data:; frame-src https: http:; connect-src https: http:; font-src https: data:; base-uri 'none'; form-action https: http:; frame-ancestors 'self'",
      "Referrer-Policy": "strict-origin-when-cross-origin",
      "X-Content-Type-Options": "nosniff",
    },
  });
};
