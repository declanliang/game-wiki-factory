/// <reference types="@cloudflare/workers-types" />

const AD_FORMATS = [
  "nativeBanner",
  "nativeBannerMobile",
  "banner728x90",
  "banner300x250",
  "banner468x60",
  "sidebar160x600",
  "sidebar160x300",
  "mobile320x50",
] as const;

type AdFormat = (typeof AD_FORMATS)[number];

type Env = {
  ASSETS: Fetcher;
  AD_NATIVE_BANNER_B64?: string;
  AD_NATIVE_BANNER_MOBILE_B64?: string;
  AD_BANNER_728X90_B64?: string;
  AD_BANNER_300X250_B64?: string;
  AD_BANNER_468X60_B64?: string;
  AD_SIDEBAR_160X600_B64?: string;
  AD_SIDEBAR_160X300_B64?: string;
  AD_MOBILE_320X50_B64?: string;
};

const ENV_KEY: Record<AdFormat, keyof Env> = {
  nativeBanner: "AD_NATIVE_BANNER_B64",
  nativeBannerMobile: "AD_NATIVE_BANNER_MOBILE_B64",
  banner728x90: "AD_BANNER_728X90_B64",
  banner300x250: "AD_BANNER_300X250_B64",
  banner468x60: "AD_BANNER_468X60_B64",
  sidebar160x600: "AD_SIDEBAR_160X600_B64",
  sidebar160x300: "AD_SIDEBAR_160X300_B64",
  mobile320x50: "AD_MOBILE_320X50_B64",
};

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

function hasValidBase64(value: string | undefined): boolean {
  return Boolean(decodeSnippet(value));
}

function availability(env: Env): Response {
  return Response.json(
    Object.fromEntries(
      AD_FORMATS.map((format) => [format, hasValidBase64(env[ENV_KEY[format]] as string | undefined)]),
    ),
    {
      headers: {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
      },
    },
  );
}

function adResponse(format: AdFormat, env: Env): Response {
  const snippet = decodeSnippet(env[ENV_KEY[format]] as string | undefined);
  if (!snippet) return new Response("Not found", { status: 404 });

  const native = format === "nativeBanner" || format === "nativeBannerMobile";
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
}

export default {
  fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/api/ads/availability") {
      return availability(env);
    }

    if (request.method === "GET") {
      const match = url.pathname.match(/^\/api\/ads\/([^/]+)\/?$/);
      if (match) {
        const format = match[1];
        return isAdFormat(format) ? adResponse(format, env) : new Response("Not found", { status: 404 });
      }
    }

    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;
