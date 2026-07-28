#!/usr/bin/env node
// Converts/copies asset files into public/ and fills public/manifest.json — the
// mechanical-fill half of what used to be Part 1's "素材文件" step.
//
// Requires ffmpeg on PATH for image conversion (hero → webp, single-logo → favicon
// sizes). Resolution/quality of the source images is the human's responsibility
// (deliberately out of scope here, per an explicit call on this) — this script only
// converts format/size, it doesn't judge whether a source image looks good enough.
//
// Usage: npm run process:assets

import { execSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { resolveIntakeConfig } from "./lib/resolve-config.mjs";

const root = process.cwd();
const ok = (msg) => console.log(`\x1b[32m✓\x1b[0m ${msg}`);
const info = (msg) => console.log(`\x1b[36mi\x1b[0m ${msg}`);
const warn = (msg) => console.warn(`\x1b[33m!\x1b[0m ${msg}`);

function hasFfmpeg() {
  try {
    execSync("ffmpeg -version", { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

// HSL string like "217 91% 53%" (the format used in globals.css) -> "#rrggbb" for manifest.json.
function hslStringToHex(hslStr) {
  const [h, s, l] = hslStr.split(/\s+/).map((v) => Number.parseFloat(v));
  const sFrac = s / 100;
  const lFrac = l / 100;
  const c = (1 - Math.abs(2 * lFrac - 1)) * sFrac;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = lFrac - c / 2;
  let [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  const toHex = (v) => Math.round((v + m) * 255).toString(16).padStart(2, "0");
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

// Common bold sans-serif font paths, checked in order — used only by the "no real
// favicon provided" fallback (drawtext needs an actual font file; Windows ffmpeg
// builds don't ship fontconfig, so a guessable system path is the only reliable option).
function findAvailableFont() {
  const candidates = [
    "C:\\Windows\\Fonts\\arialbd.ttf",
    "C:\\Windows\\Fonts\\segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
  ];
  return candidates.find((p) => fs.existsSync(p)) ?? null;
}

// HERO_IMAGE_SOURCE/FAVICON_SET_DIR/LOGO_SOURCE are already resolved against intake/
// conventions (intake/hero/, intake/favicon/, intake/hero.<ext>, intake/logo.<ext>) by the
// time we see them here — see scripts/lib/resolve-config.mjs. This script itself no longer
// needs to know whether a path came from an explicit new-site.env value or a convention.
const { env } = resolveIntakeConfig(root);
const ffmpegAvailable = hasFfmpeg();
if (!ffmpegAvailable) warn("没有检测到 ffmpeg，hero 转 webp / 单张 logo 生成 favicon 会跳过（favicon 整套复制不受影响）。");

// Read once, reused both by the initials-icon background color and by manifest.json's
// theme_color at the end of this script (same fixed value, --nav-theme in globals.css).
const themeConfigPath = path.join(root, "src", "config", "theme.ts");
const themeConfig = fs.readFileSync(themeConfigPath, "utf-8");
const manifestColorMatch = themeConfig.match(/THEME_MANIFEST_COLOR\s*=\s*["'](#[0-9a-f]{6})["']/i);
const navThemeHex = manifestColorMatch?.[1] || "#6842c2";

// --- 1. Hero image -> public/images/hero.webp -----------------------------------
if (env.HERO_IMAGE_SOURCE) {
  const src = path.join(root, env.HERO_IMAGE_SOURCE);
  if (!fs.existsSync(src)) {
    warn(`HERO_IMAGE_SOURCE（${env.HERO_IMAGE_SOURCE}）不存在，跳过 hero 图`);
  } else if (ffmpegAvailable) {
    const dest = path.join(root, "public", "images", "hero.webp");
    execSync(`ffmpeg -y -i "${src}" "${dest}"`, { stdio: "ignore" });
    ok(`hero 图已转换：${env.HERO_IMAGE_SOURCE} → public/images/hero.webp`);
  }
}

// --- 1b. Official gameplay gallery -> reusable article/card media ----------------
// Basic Info supplies only platform/creator images here (Roblox gallery or Steam
// screenshots). They are presentation aids, not evidence for an article claim.
const gameplaySourceDir = path.join(root, "intake", "gameplay-media");
const gameplayDestDir = path.join(root, "public", "images", "gameplay");
fs.rmSync(gameplayDestDir, { recursive: true, force: true });
if (fs.existsSync(gameplaySourceDir) && ffmpegAvailable) {
  fs.mkdirSync(gameplayDestDir, { recursive: true });
  const gameplaySources = fs.readdirSync(gameplaySourceDir, { withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => path.join(gameplaySourceDir, entry.name))
    .slice(0, 5);
  for (const [index, src] of gameplaySources.entries()) {
    const dest = path.join(gameplayDestDir, `gameplay-${index + 1}.webp`);
    execSync(
      `ffmpeg -y -i "${src}" -vf "scale='min(1400,iw)':-2" -quality 82 "${dest}"`,
      { stdio: "ignore" },
    );
  }
  ok(`${gameplaySources.length} 张官方游戏图已处理为文章/卡片媒体`);
} else if (fs.existsSync(gameplaySourceDir)) {
  warn("存在 gameplay-media，但没有 ffmpeg，文章将正常发布但不展示附加截图");
}

// --- 2. Favicon: FAVICON_SET_DIR (copy) takes priority over LOGO_SOURCE (generate) ---
const FAVICON_PNG_SIZES = [
  ["favicon-16x16.png", 16],
  ["favicon-32x32.png", 32],
  ["apple-touch-icon.png", 180],
  ["android-chrome-192x192.png", 192],
  ["android-chrome-512x512.png", 512],
];

// ffmpeg's .ico muxer only supports one resolution per file (unlike a "real" multi-res
// .ico) — good enough as a fallback, but a proper multi-size .ico is what FAVICON_SET_DIR
// (a real favicon generator's output) gives you. This is the best-effort, less-tested path.
function generateFaviconsFromSource(src, label) {
  for (const [name, size] of FAVICON_PNG_SIZES) {
    execSync(`ffmpeg -y -i "${src}" -vf scale=${size}:${size} "${path.join(root, "public", name)}"`, { stdio: "ignore" });
  }
  execSync(`ffmpeg -y -i "${src}" -vf scale=48:48 "${path.join(root, "public", "favicon.ico")}"`, { stdio: "ignore" });
  ok(`favicon 整套已从${label}生成 —— 单分辨率 .ico，不如现成生成器的多分辨率版，能用但不是最佳`);
}

if (env.FAVICON_SET_DIR) {
  const dir = path.join(root, env.FAVICON_SET_DIR);
  if (!fs.existsSync(dir)) {
    warn(`FAVICON_SET_DIR（${env.FAVICON_SET_DIR}）不存在，跳过 favicon`);
  } else {
    const knownFiles = [...FAVICON_PNG_SIZES.map(([name]) => name), "favicon.ico"];
    let copied = 0;
    for (const name of knownFiles) {
      const src = path.join(dir, name);
      if (fs.existsSync(src)) {
        fs.copyFileSync(src, path.join(root, "public", name));
        copied++;
      }
    }
    ok(`favicon 整套已复制（${copied}/${knownFiles.length} 个文件，来自 ${env.FAVICON_SET_DIR}）`);
  }
} else if (env.LOGO_SOURCE && fs.existsSync(path.join(root, env.LOGO_SOURCE))) {
  if (ffmpegAvailable) generateFaviconsFromSource(path.join(root, env.LOGO_SOURCE), `单张 logo（${env.LOGO_SOURCE}）`);
} else if (env.LOGO_SOURCE) {
  warn(`LOGO_SOURCE（${env.LOGO_SOURCE}）不存在，跳过 favicon`);
} else if (ffmpegAvailable && env.GAME_NAME) {
  // Neither a real favicon set nor a source logo was provided — instead of leaving the
  // template's generic placeholder icon (unrelated to this game), synthesize one using
  // the same "first 2 chars of the game name" rule as the header brand badge
  // (src/components/site.tsx), so the two look consistent even without real art.
  const initials = env.GAME_NAME.trim().slice(0, 2).toUpperCase() || "??";
  const fontFile = findAvailableFont();
  if (!fontFile) {
    info("没有配置 FAVICON_SET_DIR/LOGO_SOURCE，且找不到可用字体来自动生成首字母图标，favicon 保留模板占位图");
  } else {
    const tmpSrc = path.join(os.tmpdir(), `favicon-source-${Date.now()}.png`);
    try {
      const fontFileEscaped = fontFile.replace(/\\/g, "/").replace(/:/g, "\\:");
      execSync(
        `ffmpeg -y -f lavfi -i "color=c=${navThemeHex}:s=512x512" -vf "drawtext=fontfile='${fontFileEscaped}':text='${initials}':fontcolor=white:fontsize=260:x=(w-text_w)/2:y=(h-text_h)/2" -frames:v 1 "${tmpSrc}"`,
        { stdio: "ignore" }
      );
      generateFaviconsFromSource(tmpSrc, `游戏名首字母自动生成（${initials}）`);
    } catch {
      warn("ffmpeg 生成首字母占位图标失败（字体或滤镜不受支持），favicon 保留模板占位图");
    } finally {
      if (fs.existsSync(tmpSrc)) fs.unlinkSync(tmpSrc);
    }
  }
} else {
  info("没有配置 FAVICON_SET_DIR 或 LOGO_SOURCE，favicon 保留模板占位图");
}

// --- 3. YouTube trailer thumbnail ------------------------------------------------
if (env.YOUTUBE_VIDEO_ID) {
  const url = `https://i.ytimg.com/vi/${env.YOUTUBE_VIDEO_ID}/hqdefault.jpg`;
  const res = await fetch(url);
  if (res.ok) {
    const buf = Buffer.from(await res.arrayBuffer());
    fs.writeFileSync(path.join(root, "public", "images", "hero-trailer-thumbnail.jpg"), buf);
    ok(`预告片缩略图已下载（hqdefault，${env.YOUTUBE_VIDEO_ID}）`);
  } else {
    warn(`预告片缩略图下载失败：HTTP ${res.status}`);
  }
}

// --- 4. manifest.json --------------------------------------------------------------
const enPath = path.join(root, "src", "locales", "en.json");
const en = JSON.parse(fs.readFileSync(enPath, "utf-8"));
const manifestPath = path.join(root, "public", "manifest.json");
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
manifest.name = `${en.site.name} Wiki`;
manifest.short_name = en.site.shortName;
manifest.description = en.site.description;
manifest.theme_color = navThemeHex;
fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
ok("manifest.json 已更新（name/short_name/description/theme_color）");
