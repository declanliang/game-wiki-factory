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
import path from "node:path";
import { resolveSiteUrl } from "../src/config/site-url.mjs";

const root = process.cwd();
let errors = 0;
const fail = (msg) => { console.error(`\x1b[31m✗\x1b[0m ${msg}`); errors++; };
const ok = (msg) => console.log(`\x1b[32m✓\x1b[0m ${msg}`);
const step = (msg) => console.log(`\n\x1b[1m${msg}\x1b[0m`);

const args = process.argv.slice(2);
const skipBuild = args.includes("--skip-build");
const portArgIdx = args.indexOf("--port");
const port = portArgIdx !== -1 ? Number(args[portArgIdx + 1]) : 3100;

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

function inspectHtmlMetadata(html, label, expectedOrigin = null) {
  const title = html.match(/<title[^>]*>([^<]+)<\/title>/i)?.[1]?.trim() || "";
  const ogUrl = extractMetaContent(html, "og:url");
  const ogImage = extractMetaContent(html, "og:image");
  const twitterImage = extractMetaContent(html, "twitter:image");
  if (!title) fail(`${label}返回了 HTML，但没有非空 <title>；metadata 可能渲染失败，请检查 NEXT_PUBLIC_SITE_URL 和部署日志`);
  else ok(`${label}<title> = ${title}`);
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
  return { title, ogUrl, ogImage, twitterImage };
}

function inspectOriginDocument(text, label, expectedOrigin) {
  const absoluteUrls = text.match(/https?:\/\/[^\s<"']+/gi) || [];
  if (absoluteUrls.length === 0) {
    fail(`${label}没有找到绝对 URL`);
    return;
  }
  const bad = absoluteUrls.filter((value) => {
    try {
      const origin = new URL(value.replace(/[),.;]+$/, "")).origin;
      if (["http://www.sitemaps.org", "http://www.w3.org"].includes(origin)) return false;
      return origin !== expectedOrigin;
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
        const res = await fetch(url);
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

// Spawning "npx"/"npx.cmd" needs shell:true on Windows (they're .cmd shell scripts, not
// PE executables — Node's spawn throws EINVAL trying to exec one directly, confirmed by
// testing, not just theoretical) and shell:true is what triggers Node's DEP0190 warning
// (a shell re-tokenizing an args array reopens the injection/quoting risk the array form
// exists to avoid). Sidestepping npx entirely fixes both: `next`'s actual entry point is a
// plain Node script (has a `#!/usr/bin/env node` shebang, not a native binary), so running
// it as `node <that file> start -p <port>` needs no shell on any OS.
const nextBin = path.join(root, "node_modules", "next", "dist", "bin", "next");
const server = spawn(process.execPath, [nextBin, "start", "-p", String(port)], { cwd: root, stdio: "pipe" });
let serverStderr = "";
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
  await waitForServer(`http://localhost:${port}/`, 30000);

  const sitemapRes = await fetch(`http://localhost:${port}/sitemap.xml`);
  let sitemapXml = "";
  if (!sitemapRes.ok) {
    fail(`sitemap.xml 请求失败：HTTP ${sitemapRes.status}`);
  } else {
    sitemapXml = await sitemapRes.text();
    const locs = [...sitemapXml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
    let badCount = 0;
    for (const loc of locs) {
      const url = new URL(loc);
      const res = await fetch(`http://localhost:${port}${url.pathname}${url.search}`);
      if (res.status !== 200) {
        fail(`${url.pathname} 返回 ${res.status}（期望 200）`);
        badCount++;
      }
    }
    if (badCount === 0) ok(`sitemap.xml 里全部 ${locs.length} 条 URL 都返回 200`);
  }

  const homeRes = await fetch(`http://localhost:${port}/`);
  const homeHtml = await homeRes.text();
  const metadata = inspectHtmlMetadata(homeHtml, "本地生产首页：");
  if (metadata.ogUrl) {
    const expectedOrigin = new URL(metadata.ogUrl).origin;
    if (sitemapXml) inspectOriginDocument(sitemapXml, "本地 sitemap.xml", expectedOrigin);
    const robotsRes = await fetch(`http://localhost:${port}/robots.txt`);
    if (!robotsRes.ok) fail(`robots.txt 请求失败：HTTP ${robotsRes.status}`);
    else inspectOriginDocument(await robotsRes.text(), "本地 robots.txt", expectedOrigin);
  }

  // Next.js's Metadata API renders this attribute as `hrefLang` (camelCase) in the actual
  // HTML output, not the lowercase `hreflang` its own name would suggest — case-insensitive
  // match so this doesn't silently under-report real, correctly-rendered tags as missing.
  const hreflangs = [...homeHtml.matchAll(/rel="alternate"\s+hreflang="([^"]+)"/gi)].map((m) => m[1]);
  if (hreflangs.length > 0) ok(`hreflang 标签：${hreflangs.join(", ")}`);
  else console.log("  （没有 hreflang 标签 —— 单语言站点是正常的，多语言站点应该有）");
} catch (err) {
  fail(`服务检查失败：${err.message}${serverStderr ? `\n${serverStderr}` : ""}`);
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
    const live = {};
    for (const p of ["/", "/sitemap.xml", "/robots.txt"]) {
      try {
        const res = await fetch(`${siteUrl}${p}`);
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
    if (live["/"]) {
      const metadata = inspectHtmlMetadata(live["/"], "线上首页：", siteUrl);
      const hreflangs = [...live["/"].matchAll(/rel="alternate"\s+hreflang="([^"]+)"/gi)].map((match) => match[1]);
      if (hreflangs.length > 0) ok(`线上 hreflang 标签：${hreflangs.join(", ")}`);
      else fail("线上首页没有 hreflang 标签；多语言 metadata 可能渲染失败");
      if (!metadata.title || !metadata.ogUrl) {
        fail("线上首页虽然返回 200，但 metadata 不完整；请检查 NEXT_PUBLIC_SITE_URL 和 Vercel Function 日志");
      }
    }
    if (live["/sitemap.xml"]) inspectOriginDocument(live["/sitemap.xml"], "线上 sitemap.xml", siteUrl);
    if (live["/robots.txt"]) inspectOriginDocument(live["/robots.txt"], "线上 robots.txt", siteUrl);
  }
}

console.log(`\n${errors} error(s).`);
process.exit(errors > 0 ? 1 : 0);
