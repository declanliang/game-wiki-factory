#!/usr/bin/env node
// Full-site verification with zero AI judgment — this is doc/新游戏上站提示词流程.md
// Part 5, as a script: every check there is already a command someone reads the
// output of and either says "looks fine" or "fix X"; a script can make that same
// pass/fail call without a human in the loop.
//
// Usage:
//   npm run verify:site                 # build + start + check everything
//   npm run verify:site -- --skip-build # reuse an existing .next build
//   npm run verify:site -- --port 3100  # default port is 3100 (avoid clashing with `next dev` on 3000)
//
// Exits non-zero if anything failed — treat this like a CI job, not something to
// eyeball and shrug off.

import { execSync, spawn } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { resolveSiteUrl } from "../src/config/site-url.mjs";

const root = process.cwd();
let errors = 0;
const fail = (msg) => { console.error(`\x1b[31m✗\x1b[0m ${msg}`); errors++; };
const ok = (msg) => console.log(`\x1b[32m✓\x1b[0m ${msg}`);
const step = (msg) => console.log(`\n\x1b[1m${msg}\x1b[0m`);
const REQUIRED_HREFLANGS = ["en", "es", "de", "fr", "ja", "x-default"];

function verifyRequiredHreflangs(values, label) {
  const actual = new Set(values.map((value) => value.toLowerCase()));
  const missing = REQUIRED_HREFLANGS.filter((value) => !actual.has(value));
  const unexpected = [...actual].filter((value) => !REQUIRED_HREFLANGS.includes(value));
  if (missing.length) fail(`${label} 缺少固定语言 hreflang：${missing.join(", ")}`);
  if (unexpected.length) fail(`${label} 包含契约外 hreflang：${unexpected.join(", ")}`);
  if (!missing.length && !unexpected.length) ok(`${label} 固定五语言与 x-default 完整`);
}

const args = process.argv.slice(2);
const skipBuild = args.includes("--skip-build");
const portArgIdx = args.indexOf("--port");
const configuredPort = portArgIdx !== -1 ? Number(args[portArgIdx + 1]) : Number(process.env.GAMEWIKI_VERIFY_PORT || 3100);

async function findAvailablePort() {
  const probe = net.createServer();
  probe.unref();
  return await new Promise((resolve, reject) => {
    probe.once("error", reject);
    probe.listen({ host: "127.0.0.1", port: 0 }, () => {
      const address = probe.address();
      const availablePort = typeof address === "object" && address ? address.port : null;
      probe.close((err) => {
        if (err) reject(err);
        else if (!availablePort) reject(new Error("无法分配本地验证端口"));
        else resolve(availablePort);
      });
    });
  });
}

if (!Number.isInteger(configuredPort) || configuredPort < 0 || configuredPort > 65535) {
  throw new Error(`无效的验证端口：${configuredPort}`);
}
const port = configuredPort === 0 ? await findAvailablePort() : configuredPort;
const localOrigin = `http://127.0.0.1:${port}`;

function run(cmd, label) {
  try {
    execSync(cmd, { cwd: root, stdio: "pipe", encoding: "utf-8" });
    ok(label);
    return true;
  } catch (err) {
    fail(`${label} 失败：\n${String(err.stdout || "") + String(err.stderr || err.message || "")}`);
    return false;
  }
}

// --- 1. 残留占位符扫描（__XXX__）------------------------------------------------
step("1. 残留占位符扫描");
function walkFiles(dir, exts) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walkFiles(full, exts));
    else if (exts.some((e) => entry.name.endsWith(e))) out.push(full);
  }
  return out;
}
const scanTargets = [
  ...walkFiles(path.join(root, "src"), [".ts", ".tsx", ".json"]),
  path.join(root, "public", "manifest.json"),
].filter((f) => fs.existsSync(f));
let placeholderHits = 0;
for (const file of scanTargets) {
  const matches = fs.readFileSync(file, "utf-8").match(/__[A-Z_]+__/g);
  if (matches) {
    placeholderHits += matches.length;
    fail(`${path.relative(root, file)} 里还有占位符：${[...new Set(matches)].join(", ")}`);
  }
}
if (placeholderHits === 0) ok("没有残留的 __XXX__ 占位符");

// --- 2. 类型检查 ----------------------------------------------------------------
step("2. 类型检查");
// A template upgrade can remove a route while an older `.next/types` tree still
// imports it.  Normal verification is about to rebuild, so discard only those
// generated types before tsc; `--skip-build` keeps the known-current build intact.
if (!skipBuild) fs.rmSync(path.join(root, ".next", "types"), { recursive: true, force: true });
run("npx tsc --noEmit", "npx tsc --noEmit");

// --- 3. 配置同步检查 -------------------------------------------------------------
step("3. 配置同步检查");
run("node scripts/check-config-sync.mjs", "npm run check:config");

// --- 4. 生产构建 ----------------------------------------------------------------
if (!skipBuild) {
  step("4. 生产构建");
  if (!run("npm run build", "npm run build")) {
    console.log(`\n构建失败，后面依赖构建产物的检查（sitemap/og:image）跳过。\n${errors} error(s).`);
    process.exit(1);
  }
} else {
  step("4. 生产构建（--skip-build，假设 .next 已经是最新的）");
}

// --- 5+6. 起本地服务，逐条检查 sitemap URL + og:image/twitter:image + hreflang -------
step(`5-6. 启动本地服务（端口 ${port}），检查 sitemap / og:image / hreflang`);

function extractMetaContent(html, key) {
  // Isolate the whole <meta ...> tag first, then pull content= out of it — attribute
  // order (property/name before or after content) isn't guaranteed, so a regex that
  // assumes one fixed order is fragile.
  const tagMatch = html.match(new RegExp(`<meta[^>]*(?:property|name)=["']${key}["'][^>]*>`, "i"));
  if (!tagMatch) return null;
  const contentMatch = tagMatch[0].match(/content=["']([^"']+)["']/);
  return contentMatch ? contentMatch[1] : null;
}

function extractLinkHref(html, rel) {
  const tag = html.match(new RegExp(`<link[^>]*rel=["']${rel}["'][^>]*>`, "i"))?.[0];
  return tag?.match(/href=["']([^"']+)["']/i)?.[1] ?? null;
}

function inspectStructuredPageUrls(html, pageUrl) {
  let issues = 0;
  const parsedPage = new URL(pageUrl);
  const firstSegment = parsedPage.pathname.split("/").filter(Boolean)[0];
  const locale = ["en", "es", "de", "fr", "ja"].includes(firstSegment) ? firstSegment : "en";
  const localeBase = `${parsedPage.origin}/${locale}`;
  const isLocaleUrl = (value) => {
    try {
      const parsed = new URL(value);
      return parsed.origin === parsedPage.origin && (parsed.href === localeBase || parsed.href.startsWith(`${localeBase}/`));
    } catch { return false; }
  };
  for (const match of html.matchAll(/<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi)) {
    let data;
    try { data = JSON.parse(match[1]); } catch { continue; }
    const nodes = data?.["@graph"] || [data];
    for (const node of nodes) {
      if (node?.["@type"] === "Article" && new URL(node.mainEntityOfPage).href !== parsedPage.href) {
        fail(`${parsedPage.pathname} Article.mainEntityOfPage 未使用页面 canonical：${node.mainEntityOfPage}`);
        issues++;
      }
      if (["BreadcrumbList", "ItemList"].includes(node?.["@type"])) {
        for (const item of node.itemListElement || []) {
          const value = item.item || item.url;
          if (value && !isLocaleUrl(value)) {
            fail(`${parsedPage.pathname} ${node["@type"]} 含错误 locale URL：${value}`);
            issues++;
          }
        }
      }
    }
  }
  return issues;
}

function inspectHtmlMetadata(html, label, expectedOrigin = null, expectedPageUrl = null) {
  const title = html.match(/<title[^>]*>([^<]+)<\/title>/i)?.[1]?.trim() || "";
  const canonical = extractLinkHref(html, "canonical");
  const ogUrl = extractMetaContent(html, "og:url");
  const ogImage = extractMetaContent(html, "og:image");
  const twitterImage = extractMetaContent(html, "twitter:image");
  if (!title) fail(`${label}返回了 HTML，但没有非空 <title>；metadata 可能渲染失败，请检查 NEXT_PUBLIC_SITE_URL 和部署日志`);
  else ok(`${label}<title> = ${title}`);
  if (!canonical) fail(`${label}HTML 里没有找到 canonical`);
  else if (expectedPageUrl && new URL(canonical).href !== new URL(expectedPageUrl).href) {
    fail(`${label}canonical 为 ${canonical}，期望 self-canonical ${expectedPageUrl}`);
  } else ok(`${label}canonical = ${canonical}`);
  for (const [key, value] of [["og:url", ogUrl], ["og:image", ogImage], ["twitter:image", twitterImage]]) {
    if (!value) fail(`${label}HTML 里没有找到 ${key}`);
    else if (!/^https?:\/\//i.test(value)) fail(`${label}${key} 不是绝对 HTTP(S) URL：${value}`);
    else if (expectedOrigin && new URL(value).origin !== expectedOrigin) {
      fail(`${label}${key} origin 为 ${new URL(value).origin}，期望 ${expectedOrigin}`);
    } else ok(`${label}${key} = ${value}`);
  }
  if (/Application error|metadata render error|An error occurred in the Server Components render/i.test(html)) {
    fail(`${label}HTML 包含 Next.js/metadata 运行时错误标记`);
  }
  return { title, canonical, ogUrl, ogImage, twitterImage };
}

function inspectOriginDocument(text, label, expectedOrigin) {
  const absoluteUrls = text.match(/https?:\/\/[^\s<"']+/gi) || [];
  if (absoluteUrls.length === 0) {
    fail(`${label}没有找到绝对 URL`);
    return;
  }
  const bad = absoluteUrls.filter((value) => {
    try {
      const parsed = new URL(value.replace(/[),.;]+$/, ""));
      const origin = parsed.origin;
      if (["http://www.sitemaps.org", "http://www.w3.org"].includes(origin)) return false;
      return origin !== expectedOrigin || parsed.pathname.startsWith("//");
    }
    catch { return true; }
  });
  if (bad.length > 0) fail(`${label}包含非规范 origin：${[...new Set(bad)].slice(0, 3).join(", ")}`);
  else ok(`${label}中的绝对 URL 全部使用 ${expectedOrigin}`);
}

function waitForServer(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const attempt = async () => {
      try {
        const res = await fetch(url, { redirect: "manual" });
        if (res.status < 500) return resolve();
      } catch {
        // not up yet
      }
      if (Date.now() > deadline) return reject(new Error("等待服务启动超时"));
      setTimeout(attempt, 500);
    };
    attempt();
  });
}

const nextBin = path.join(root, "node_modules", "next", "dist", "bin", "next");
const standaloneRoot = path.join(root, ".next", "standalone");
const standaloneServer = path.join(standaloneRoot, "server.js");
let serverArgs = [nextBin, "start", "-p", String(port)];
let serverCwd = root;
let serverEnv = process.env;

if (fs.existsSync(path.join(root, "out"))) {
  serverArgs = [path.join(root, "scripts", "static-export-server.mjs"), String(port)];
} else if (fs.existsSync(standaloneServer)) {
  // Next's standalone trace intentionally omits public and .next/static. Production
  // containers copy both next to server.js, so reproduce that exact runtime for QA.
  const publicSource = path.join(root, "public");
  if (fs.existsSync(publicSource)) {
    fs.cpSync(publicSource, path.join(standaloneRoot, "public"), { recursive: true, force: true });
  }
  const staticSource = path.join(root, ".next", "static");
  if (fs.existsSync(staticSource)) {
    fs.cpSync(staticSource, path.join(standaloneRoot, ".next", "static"), { recursive: true, force: true });
  }
  serverArgs = [standaloneServer];
  serverCwd = standaloneRoot;
  // Next's standalone server constructs middleware rewrite origins from its
  // bind hostname.  Binding to 127.0.0.1 makes next-intl see two different
  // origins (`127.0.0.1` and its internal `localhost`) and can redirect the
  // default locale forever.  The standalone production default avoids that;
  // checks still connect through loopback below and the random port lives only
  // for this short-lived QA process.
  serverEnv = { ...process.env, HOSTNAME: "0.0.0.0", PORT: String(port) };
}

const server = spawn(process.execPath, serverArgs, { cwd: serverCwd, env: serverEnv, stdio: "pipe" });
let serverStdout = "";
let serverStderr = "";
server.stdout.on("data", (d) => { serverStdout += d.toString(); });
server.stderr.on("data", (d) => { serverStderr += d.toString(); });

// Next's production server doesn't stay a direct child of the spawned process either
// (worker process), so `server.kill()` doesn't reliably reach the real listener. Instead,
// look up whatever process actually holds the port and kill that — same pattern as
// manually clearing a stuck dev-server port.
function killServer() {
  if (process.platform === "win32") {
    try {
      const pids = execSync(
        `powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique"`,
        { encoding: "utf-8" },
      ).trim().split(/\r?\n/).filter(Boolean);
      for (const pid of pids) {
        try { execSync(`taskkill /pid ${pid} /F`, { stdio: "ignore" }); } catch { /* already dead */ }
      }
    } catch { /* nothing listening, or lookup failed — nothing more we can do */ }
  } else {
    server.kill();
  }
}

try {
  await waitForServer(`${localOrigin}/`, 30000);

  const rootRes = await fetch(`${localOrigin}/`, { redirect: "manual" });
  const rootLocation = rootRes.headers.get("location");
  if (rootRes.status !== 301 || !rootLocation || new URL(rootLocation, localOrigin).pathname !== "/en") {
    fail(`根路径应以 301 跳转到 /en，实际为 HTTP ${rootRes.status} Location=${rootLocation || "缺失"}`);
  } else {
    ok("根路径以 301 跳转到 /en");
  }

  const sitemapRes = await fetch(`${localOrigin}/sitemap.xml`);
  let sitemapXml = "";
  if (!sitemapRes.ok) {
    fail(`sitemap.xml 请求失败：HTTP ${sitemapRes.status}`);
  } else {
    sitemapXml = await sitemapRes.text();
    const locs = [...sitemapXml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
    const hreflangTargets = [...sitemapXml.matchAll(/<xhtml:link[^>]+href=["']([^"']+)["']/g)].map((m) => m[1]);
    const sitemapHreflangs = [...sitemapXml.matchAll(/<xhtml:link[^>]+hreflang=["']([^"']+)["']/gi)].map((m) => m[1]);
    verifyRequiredHreflangs(sitemapHreflangs, "本地 sitemap.xml");
    const allTargets = [...new Set([...locs, ...hreflangTargets])];
    let badCount = 0;
    for (const target of allTargets) {
      const url = new URL(target);
      if (url.pathname.startsWith("//")) {
        fail(`sitemap URL 域名后含双斜杠：${target}`);
        badCount++;
        continue;
      }
      const res = await fetch(`${localOrigin}${url.pathname}${url.search}`, { redirect: "manual" });
      if (res.status !== 200) {
        fail(`${url.pathname} 返回 ${res.status}（期望直接 200，不允许跳转）`);
        badCount++;
      } else if ((res.headers.get("content-type") || "").includes("text/html")) {
        const html = await res.text();
        const canonical = extractLinkHref(html, "canonical");
        if (!canonical || new URL(canonical).href !== url.href) {
          fail(`${url.pathname} canonical 为 ${canonical || "缺失"}，期望 ${url.href}`);
          badCount++;
        }
        badCount += inspectStructuredPageUrls(html, url.href);
      }
    }
    if (badCount === 0) ok(`sitemap.xml 的 ${locs.length} 个 loc 和 ${hreflangTargets.length} 个 hreflang 目标均为 self-canonical 且直接返回 200`);
  }

  const sitemapLocs = [...sitemapXml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);
  const homeUrl = sitemapLocs.find((value) => new URL(value).pathname === "/en") || sitemapLocs[0] || null;
  const homePath = homeUrl ? new URL(homeUrl).pathname : "/en";
  const homeRes = await fetch(`${localOrigin}${homePath}`, { redirect: "manual" });
  if (homeRes.status !== 200) fail(`本地生产首页 ${homePath} 返回 ${homeRes.status}（期望直接 200）`);
  const homeHtml = await homeRes.text();
  const metadata = inspectHtmlMetadata(homeHtml, "本地生产首页：", null, homeUrl);
  if (metadata.ogUrl) {
    const expectedOrigin = new URL(metadata.ogUrl).origin;
    if (sitemapXml) inspectOriginDocument(sitemapXml, "本地 sitemap.xml", expectedOrigin);
    const robotsRes = await fetch(`${localOrigin}/robots.txt`);
    if (!robotsRes.ok) fail(`robots.txt 请求失败：HTTP ${robotsRes.status}`);
    else inspectOriginDocument(await robotsRes.text(), "本地 robots.txt", expectedOrigin);
  }

  // Next.js's Metadata API renders this attribute as `hrefLang` (camelCase) in the actual
  // HTML output, not the lowercase `hreflang` its own name would suggest — case-insensitive
  // match so this doesn't silently under-report real, correctly-rendered tags as missing.
  const hreflangs = [...homeHtml.matchAll(/rel="alternate"\s+hreflang="([^"]+)"/gi)].map((m) => m[1]);
  verifyRequiredHreflangs(hreflangs, "本地首页");
} catch (err) {
  const diagnostics = `${serverStdout}${serverStderr}`;
  fail(`服务检查失败：${err.message}${diagnostics ? `\n${diagnostics}` : ""}`);
} finally {
  killServer();
}

// --- 7. 部署域名检查（--deploy，上线前才需要，本地生成阶段不需要）------------------
// Local generation is legitimately allowed to run with the placeholder domain (nothing
// above fails on it — og:image being an absolute example.com URL still passes the "is
// this an absolute URL" check on line ~170). This step is what actually catches "still
// pointing at the placeholder domain" before it ships, by checking the real deploy-time
// config and by hitting the real live domain, not localhost.
if (args.includes("--deploy")) {
  step("7. 部署域名检查（--deploy）");
  function loadEnvLocal() {
    const p = path.join(root, ".env.local");
    if (!fs.existsSync(p)) return {};
    const env = {};
    for (const line of fs.readFileSync(p, "utf-8").split(/\r\n|\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const eq = line.indexOf("=");
      if (eq === -1) continue;
      env[line.slice(0, eq).trim()] = line.slice(eq + 1).trim();
    }
    return env;
  }
  const configuredSiteUrl = process.env.NEXT_PUBLIC_SITE_URL || loadEnvLocal().NEXT_PUBLIC_SITE_URL || "";
  let siteUrl = "";
  if (!configuredSiteUrl) {
    fail("NEXT_PUBLIC_SITE_URL 没有设置（.env.local 或部署平台环境变量）—— 部署前必须配置成真实域名，否则 sitemap/canonical/og:image 会带着 src/config/site.ts 里的占位域名上线");
  } else {
    try { siteUrl = resolveSiteUrl(configuredSiteUrl); }
    catch (error) { fail(error.message); }
  }
  if (siteUrl && /example\.com/i.test(siteUrl)) {
    fail(`NEXT_PUBLIC_SITE_URL（${siteUrl}）还是模板占位域名 —— 换成真实部署域名再上线`);
  } else if (siteUrl) {
    ok(`NEXT_PUBLIC_SITE_URL = ${siteUrl}（规范化后）`);
    const rootResponse = await fetch(`${siteUrl}/`, { redirect: "manual" });
    const rootLocation = rootResponse.headers.get("location");
    if (rootResponse.status !== 301 || !rootLocation || new URL(rootLocation, siteUrl).pathname !== "/en") {
      fail(`线上根路径应以 301 跳转到 /en，实际为 HTTP ${rootResponse.status} Location=${rootLocation || "缺失"}`);
    } else {
      ok("线上根路径以 301 跳转到 /en");
    }
    const live = {};
    for (const p of ["/en", "/sitemap.xml", "/robots.txt"]) {
      try {
        const res = await fetch(`${siteUrl}${p}`, { redirect: "manual" });
        const body = await res.text();
        if (res.status === 200) {
          ok(`线上 ${p} 返回 200`);
          live[p] = body;
        }
        else fail(`线上 ${p} 返回 ${res.status}（期望 200）—— 确认域名已经正确部署且能公网访问`);
      } catch (err) {
        fail(`线上 ${p} 请求失败：${err.message} —— 域名是否已经解析并部署完成？`);
      }
    }
    if (live["/en"]) {
      const homeUrl = `${siteUrl}/en`;
      const metadata = inspectHtmlMetadata(live["/en"], "线上首页：", siteUrl, homeUrl);
      const hreflangs = [...live["/en"].matchAll(/rel="alternate"\s+hreflang="([^"]+)"/gi)].map((match) => match[1]);
      verifyRequiredHreflangs(hreflangs, "线上首页");
      if (!metadata.title || !metadata.ogUrl) {
        fail("线上首页虽然返回 200，但 metadata 不完整；请检查 NEXT_PUBLIC_SITE_URL 和 Cloudflare Pages 构建日志");
      }
    }
    if (live["/sitemap.xml"]) {
      inspectOriginDocument(live["/sitemap.xml"], "线上 sitemap.xml", siteUrl);
      const sitemapHreflangs = [...live["/sitemap.xml"].matchAll(/<xhtml:link[^>]+hreflang=["']([^"']+)["']/gi)].map((match) => match[1]);
      verifyRequiredHreflangs(sitemapHreflangs, "线上 sitemap.xml");
      const targets = [...new Set([
        ...[...live["/sitemap.xml"].matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]),
        ...[...live["/sitemap.xml"].matchAll(/<xhtml:link[^>]+href=["']([^"']+)["']/g)].map((match) => match[1]),
      ])];
      let badTargets = 0;
      for (const target of targets) {
        try {
          const parsed = new URL(target);
          if (parsed.pathname.startsWith("//")) throw new Error("域名后含双斜杠");
          const response = await fetch(target, { redirect: "manual" });
          if (response.status !== 200) throw new Error(`HTTP ${response.status}`);
        } catch (error) {
          fail(`线上 sitemap 目标不是直接 200：${target}（${error.message}）`);
          badTargets++;
        }
      }
      if (badTargets === 0) ok(`线上 sitemap 的 ${targets.length} 个唯一 loc/hreflang 目标全部直接返回 200`);
    }
    if (live["/robots.txt"]) inspectOriginDocument(live["/robots.txt"], "线上 robots.txt", siteUrl);
  }
}

console.log(`\n${errors} error(s).`);
process.exit(errors > 0 ? 1 : 0);
