# Cloudflare Workers Static Assets 发布

Cloudflare Pages 项目额度已满后，新任务默认发布到 Cloudflare Workers Static Assets。Factory 仍会创建或复用每个游戏自己的 Private GitHub repo，但托管部署不再创建 Pages project。

发布事务：

1. GitHub repo 必须是 Private；
2. 发布器生成本地 `wrangler.jsonc`，该文件被 `.gitignore` 忽略，不提交 Git；
3. `wrangler.jsonc` 使用 `main = "./src/worker.ts"`，`assets.directory = "./out"`，`assets.binding = "ASSETS"`；
4. `assets.not_found_handling = "404-page"`，因为模板是 Next 静态导出，不是 SPA；
5. `assets.run_worker_first = ["/api/*"]`，让 API 请求先进入 Worker，不被静态导出的 404 页面接管；
6. 发布器用最终 origin 设置 `NEXT_PUBLIC_SITE_URL`，在服务器本地执行 `npm run build`；
7. 发布器使用 `npx wrangler deploy --config wrangler.jsonc` 上传 Worker 和静态资产；
8. 发布后必须执行线上首页、metadata、canonical、sitemap、robots、广告 API 和全部 loc/hreflang 直接 200 验证。

广告 API 不是纯静态文件。模板的 `src/worker.ts` 接管 `/api/ads/availability` 和 `/api/ads/render/<format>`，从 Worker vars 读取 8 个 `AD_*_B64`，其他请求交给 `env.ASSETS.fetch(request)`。旧的 `/api/ads/<format>` 仍保留兼容匹配，但新前端只使用 `render` 路径，以避开历史静态 404 缓存。API 响应使用 `private, no-store`、`Vary: Accept` 和 CDN no-store 头；线上验收必须用浏览器 iframe 请求头检查格式路由，而不能只用默认 `curl`。

模板的 `public/_headers` 对资源采用分层缓存策略：`/_next/static/*` 是带内容 hash 的不可变构建资源，使用一年 `immutable` 缓存；`/images/*` 使用一天缓存并允许 stale-while-revalidate。HTML、SEO 文件和 `/api/*` 不使用长缓存，以便 localeRelease、内容更新和广告可用性立即生效。不要把全局 `max-age=0` 复制到 hash 静态资源，否则浏览器每次打开页面都会重新验证所有脚本和样式。

未提供 `siteUrl` 时，Factory 读取 Cloudflare account 的 workers.dev subdomain，使用 `https://<worker>.<subdomain>.workers.dev` 作为 `NEXT_PUBLIC_SITE_URL` 并自动验收。

提供正式域名时，Factory 会先用正式域名构建 canonical/sitemap，再部署到 workers.dev，并通过 Workers Custom Domains API 自动创建或复用该 hostname 到 Worker production 环境的绑定。只有 Cloudflare zone 缺失、API 权限不足、DNS 冲突或最终域名验收未通过时，回执才会保留 `hosting.status=awaiting_domain_configuration`；该状态不得声称正式域名已上线。问题处理后重试同一 Job，完成最终线上验收。

需要的凭据仍只保存在 factory 根 `.env` 或服务器 `factory.env`：

- `FACTORY_GITHUB_TOKEN`（本地也可复用 `gh auth login`）；
- `CLOUDFLARE_ACCOUNT_ID`；
- `CLOUDFLARE_API_TOKEN`，需要 Workers Scripts/Edit、Workers Routes/Custom Domains 相关权限，以及读取 workers.dev subdomain 的权限。

禁止为新站静默回退到 Cloudflare Pages、Vercel、Netlify 或 Docker 发布。
