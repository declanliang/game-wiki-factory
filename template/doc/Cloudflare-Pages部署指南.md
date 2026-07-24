# Cloudflare Pages 部署指南

这份文档记录本模板从 Vercel（Node Function 运行时）迁移到 Cloudflare Pages（纯静态导出）做了什么、为什么这么改，以及部署/排障的实际步骤。改动落在 `cloudflare-pages-template` 分支；`main` 分支（`output: "standalone"`，给 Vercel 用）未受影响。

首次实践于 `anime-expeditions` 项目（该项目由本模板生成），验证通过后回填到模板本身，让后续新建的站点也能直接选择 Cloudflare Pages 部署路径。

## 为什么要迁移

原站部署在 Vercel，`next.config.mjs` 用的是 `output: "standalone"`——即便页面内容是静态可预渲染的（所有路由都用了 `generateStaticParams`），Next.js 仍然会跑一个 Node Server 来处理每个请求，加上 `next-intl` 的 middleware 在几乎所有路径上运行，两者都会计入 Vercel Functions 的 CPU 时间。免费版额度只有 4 小时/月，容易被日常流量吃满。

站点内容本质上是纯静态的（内容来自构建时读取的 Markdown/JSON，没有请求时数据库查询、没有用户会话），所以更合理的形态是构建时把所有页面生成成 HTML 文件，直接扔在 CDN 上分发，不需要任何 Function 运行时。Cloudflare Pages 免费版对纯静态请求没有 CPU 计费，额度宽松得多。

## 核心改动

### 1. `next.config.mjs`：改用静态导出

```js
const nextConfig = {
  output: "export",          // 原来是 "standalone"
  poweredByHeader: false,
  pageExtensions: [...],
  images: { unoptimized: true },   // 静态导出没有图片优化 server，见下方"已知取舍"
};
```

原来 `headers()` 里配置的安全响应头（HSTS、X-Frame-Options 等）在静态导出下不会生效（那是给 Node server 用的），改成 `public/_headers` 文件，Cloudflare Pages 原生支持读取这个文件给所有响应加头。

### 2. 删除 `src/middleware.ts`

静态导出完全不支持 middleware。原来 middleware 唯一的作用是 next-intl 的多语言路由（`localePrefix: "as-needed"`，让默认语言 English 用裸路径 `/guide` 而不是 `/en/guide`），这个行为本质上是"请求到达时用 middleware 把 `/` 重写成 `/en`，同时保持地址栏显示裸路径"，静态导出没有请求时运行时，做不到这个重写。

**因此 `localePrefix` 也从 `"as-needed"` 改成了 `"always"`**——所有语言（包括英文）都带前缀（`/en/guide`）。这是一个**用户可见的 URL 结构变化**，如果站点之前用 `as-needed` 上线过、已被搜索引擎收录，迁移时要考虑旧链接的 SEO 权重（见下方 `_redirects` 部分）；全新站点从 Cloudflare Pages 起步则没有这层顾虑。

涉及改动的文件：
- `src/i18n/routing.ts`：`localePrefix: "always"`，`languageAlternates()` 不再对默认语言特殊处理
- `src/config/site-path.mjs`：`localizedPathname()` 不再对默认语言跳过前缀
- `src/components/language-switcher.tsx`：语言切换逻辑统一按"始终有前缀"处理，删除了依赖 middleware 读取的 `NEXT_LOCALE` cookie 设置（没有 middleware 了，这个 cookie 没有消费者）

### 3. `/api/ads/[format]/route.ts` → Cloudflare Pages Function

静态导出下 Next.js 的动态 Route Handler（尤其是 `export const dynamic = "force-dynamic"` 这种需要运行时逻辑、并且要读 server-only 环境变量避免把广告代码打进客户端 bundle 的接口）无法保留。原路由被删除，逻辑原样搬到 `functions/api/ads/[format].ts`，这是 Cloudflare Pages 的原生 Function 机制（按文件路径路由，语法接近但不是 Next.js Route Handler）：

- 广告 snippet 仍然是 server-only（存在 Cloudflare Pages 的环境变量里，不出现在客户端 bundle）
- 响应头 `Cache-Control: private, no-store` 保留，避免广告被 CDN 缓存
- 环境变量读取方式从 `process.env.X` 改成 `context.env.X`（Workers runtime 的约定）
- `functions/tsconfig.json` 单独配置，用 `@cloudflare/workers-types` 提供 `PagesFunction` 类型；主 `tsconfig.json` 把 `functions/` 目录排除，避免 Next.js 的类型检查把它当成 app 代码处理

### 4. `next-intl` 静态渲染要求：`setRequestLocale()`

静态导出下，`next-intl` 需要显式调用 `setRequestLocale(locale)`（在每个由 `generateStaticParams` 产出 `locale` 参数的页面里，构建时尽早调用），否则它的语言解析逻辑会退化到读取请求头，这在静态导出的构建阶段是不可用的，会直接报错 `couldn't be rendered statically because it used 'headers'`。

涉及文件：`src/app/[locale]/layout.tsx`、`src/app/[locale]/page.tsx`、`src/app/[locale]/[...slug]/page.tsx`、`src/components/legal-page.tsx`（about/copyright/privacy-policy/terms-of-service 四个法律页共用这一个组件）。

### 5. `robots.ts` / `sitemap.ts` 加 `force-static`

Next.js 的这两个元数据文件默认按需动态生成，静态导出要求显式声明 `export const dynamic = "force-static"`。

### 6. `public/_redirects`：旧裸路径 301 到新前缀路径

因为 `localePrefix` 改成了 `always`，`/guide`、`/about` 这类旧的（如果站点之前在 Vercel 用 `as-needed` 跑过、可能已被搜索引擎收录的）裸路径不再对应任何静态文件。用 Cloudflare Pages 原生支持的 `_redirects` 文件把它们 301 到 `/en/guide`、`/en/about`。

模板里的 `public/_redirects` 只包含固定的几条（首页、法律页），**内容分类的重定向规则需要在建站时按该游戏实际发布的分类手动补全**（文件里有 TODO 注释和示例格式）——因为 `src/config/site-plan.json` 的 `categories` 是每个新站点各自不同的，模板本身不知道。如果这个站点从 Cloudflare Pages 起步、之前从未以 `as-needed` 形式上线过，这些内容分类重定向规则可以不加。

**踩过的坑，写在这里避免重复踩**：
- `_redirects` 是**逐行从上到下匹配，第一条匹配的规则生效，并且在静态资源命中之前就会被评估**——不是"静态文件优先，找不到才走 _redirects"。
- 最早用了一条通配规则 `/:type -> /en/:type`（想省事，覆盖所有旧内容分类 slug），结果这条规则连 `/_next/static/css/*.css`、`/_next/static/chunks/*.js` 这些资源路径都当成"旧分类 slug"一起重定向了，导致页面能打开但样式/脚本全部 404，页面直接"裸奔"。
- 正确做法：**不用通配符**，把真正存在过的旧内容分类 slug（对应该站点 `src/config/navigation.ts` 里的 `CONTENT_TYPES`）逐条列出来，只重定向这些明确路径，不碰 `/_next/*`、`/api/*`、`/images/*` 等系统/资源路径。

## 已知取舍

- **图片不再走 Next.js 图片优化服务**（`images.unoptimized: true`），因为那个服务本身需要一个运行中的 server。原图需要自己保证是合理尺寸/格式（webp 等），否则会比之前多传一些字节。如果流量对图片体积敏感，后续可以考虑用 Cloudflare Images 或构建时脚本预压缩。
- **英文 URL 从裸路径变成 `/en/...` 前缀**，是这套改动里唯一真正改变对外行为的地方；老站点迁移时已用 `_redirects` 做 301 兜底，仍建议观察 Search Console 收录情况。全新站点没有这个负担。

## 部署步骤（Cloudflare Dashboard，手动操作）

> 约定：Cloudflare Pages 项目的创建、Git 集成授权（GitHub App 安装）、环境变量填写、自定义域名绑定，这几步都必须在 Dashboard 里手动完成——Cloudflare 的 API Token 走不通 GitHub OAuth 集成这一步，所以不用 API/CLI 自动化创建 Git 集成型项目。

1. **Cloudflare Dashboard → Workers & Pages → Create → Pages → Connect to Git**，选对应仓库，部署分支选该站点用于 Cloudflare Pages 的分支（如果同一个站点还在用 Vercel，注意不要选到 Vercel 用的 `output: "standalone"` 分支）。
2. **构建配置**：
   - Build command: `npm run build`
   - Build output directory: `out`
   - Root directory: 留空
3. **环境变量**（Settings → Environment variables）：
   - `NEXT_PUBLIC_SITE_URL`
   - `NEXT_PUBLIC_GOOGLE_ANALYTICS_ID` / `NEXT_PUBLIC_MICROSOFT_CLARITY_ID` / `NEXT_PUBLIC_GOOGLE_ADSENSE_ID`（如果用）
   - `AD_*_B64`（或 `AD_*`）系列——广告 snippet，建议标记为 Secret 类型，因为 `functions/api/ads/[format].ts` 会读取它们
   - 如果站点之前部署在 Vercel，以上变量可以从 Vercel 项目逐条复制过来
4. **首次部署完成后**，用 Cloudflare 分配的 `*.pages.dev` 临时域名验证：
   - 确认 `/` 返回 301 且 `Location` 为 `/en`
   - 抽查几个页面：首页、任意一个非默认语言页面、任意一个内容分类页面
   - 确认样式/脚本正常加载（打开一次浏览器 DevTools Network 面板，看有没有 301/404 的 `_next/static/*` 请求——如果有，大概率是 `_redirects` 规则又把资源路径误伤了）
   - 测试广告接口：`/api/ads/<format>` 等，确认返回正确 HTML 且响应头带 `Cache-Control: private, no-store`
   - 检查 `/sitemap.xml`、`/robots.txt`
5. **确认没问题后再接自定义域名**——这一步涉及 DNS，约定由人工在 Cloudflare 里操作，AI 不直接改 DNS 记录。
6. 如果是从 Vercel 迁移，旧的 Vercel 项目先不要立刻下线，观察 Cloudflare Pages 跑稳（收录、广告展示都正常）一段时间后再决定。

## 本地验证命令

```bash
npm run build      # 产出 out/ 目录（静态导出）
npm start           # 用零依赖本地服务器预览 out/，包含 _redirects 行为
npm run verify:site # 重建并验证 / -> /en、metadata、sitemap 和全部 hreflang
npx tsc --noEmit
npx tsc --noEmit -p functions/tsconfig.json   # 单独 typecheck Cloudflare Pages Function
```

Factory 的 Cloudflare Pages 分支会拒绝后台 `taskType: ads`。广告需在单站完成 `npm run ads:import` 校验后，由运营者把 `AD_*_B64` 手工写入 Pages Production Secret；这是当前明确的人工边界，不要复用旧 Vercel 自动化。

`wrangler pages deploy out --project-name <项目名>` 可以在本地直接把 `out/` 上传部署（Direct Upload 方式），不依赖 GitHub 集成，适合快速验证，但线上长期使用建议走 Dashboard 的 Git 集成（push 自动触发构建部署），不建议把 `wrangler deploy` 做成自动化脚本长期跑——避免绕过人工确认这一步。
