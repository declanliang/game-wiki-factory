import { getAdSnippet, isAdFormat } from "@/lib/ad-config";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ format: string }> }) {
  const { format } = await params;
  if (!isAdFormat(format)) return new Response("Not found", { status: 404 });
  const snippet = getAdSnippet(format);
  if (!snippet) return new Response("Not found", { status: 404 });
  const native = format === "nativeBanner";
  const normalizedSnippet = snippet.replace(/(<script\b[^>]*\bsrc=["'])\/\//gi, "$1https://");
  // The inert comments let deployment verification hash the exact isolated
  // snippet without exposing credentials or relying on third-party fill time.
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
