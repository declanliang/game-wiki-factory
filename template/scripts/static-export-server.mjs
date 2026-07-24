#!/usr/bin/env node

import fs from "node:fs";
import http from "node:http";
import path from "node:path";

const root = path.resolve(process.cwd(), process.env.GAMEWIKI_STATIC_DIR || "out");
const port = Number(process.env.PORT || process.argv[2] || 3000);

if (!fs.existsSync(root)) {
  throw new Error(`Static export directory does not exist: ${root}`);
}
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error(`Invalid port: ${port}`);
}

const mimeTypes = {
  ".avif": "image/avif",
  ".css": "text/css; charset=utf-8",
  ".gif": "image/gif",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".txt": "text/plain; charset=utf-8",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".xml": "application/xml; charset=utf-8",
};

function loadRedirects() {
  const redirectsPath = path.join(root, "_redirects");
  if (!fs.existsSync(redirectsPath)) return [];
  return fs.readFileSync(redirectsPath, "utf-8").split(/\r?\n/).flatMap((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) return [];
    const [source, target, statusText] = trimmed.split(/\s+/);
    const status = Number(statusText || 302);
    if (!source || !target || !Number.isInteger(status)) return [];
    if (source.endsWith("/*")) {
      return [{ source: source.slice(0, -1), target, status, splat: true }];
    }
    return [{ source, target, status, splat: false }];
  });
}

const redirects = loadRedirects();

function redirectFor(pathname) {
  for (const rule of redirects) {
    if (!rule.splat && pathname === rule.source) return rule;
    if (rule.splat && pathname.startsWith(rule.source)) {
      return { ...rule, target: rule.target.replace(":splat", pathname.slice(rule.source.length)) };
    }
  }
  return null;
}

function resolveFile(pathname) {
  let decoded;
  try { decoded = decodeURIComponent(pathname); }
  catch { return null; }
  const relative = decoded.replace(/^\/+/, "");
  const candidates = relative
    ? [relative, `${relative}.html`, path.join(relative, "index.html")]
    : ["index.html"];
  for (const candidate of candidates) {
    const resolved = path.resolve(root, candidate);
    if (resolved !== root && !resolved.startsWith(`${root}${path.sep}`)) continue;
    if (fs.existsSync(resolved) && fs.statSync(resolved).isFile()) return resolved;
  }
  return null;
}

const server = http.createServer((request, response) => {
  const url = new URL(request.url || "/", "http://localhost");
  const redirect = redirectFor(url.pathname);
  if (redirect) {
    response.writeHead(redirect.status, { Location: `${redirect.target}${url.search}` });
    response.end();
    return;
  }

  const file = resolveFile(url.pathname);
  if (!file) {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Not Found");
    return;
  }
  response.writeHead(200, {
    "Content-Type": mimeTypes[path.extname(file).toLowerCase()] || "application/octet-stream",
  });
  if (request.method === "HEAD") response.end();
  else fs.createReadStream(file).pipe(response);
});

server.listen(port, "0.0.0.0", () => {
  console.log(`Serving ${root} at http://127.0.0.1:${port}`);
});
