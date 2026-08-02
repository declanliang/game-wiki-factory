# Cloudflare Workers Static Assets 发布

Cloudflare Pages 项目额度已满后，新任务默认发布到 Cloudflare Workers Static Assets。Factory 仍会创建或复用每个游戏自己的 Private GitHub repo，但托管部署不再创建 Pages project。

发布事务：

1. GitHub repo 必须是 Private；
2. 发布器生成本地 `wrangler.jsonc`，该文件被 `.gitignore` 忽略，不提交 Git；
3. `wrangler.jsonc` 使用 `main = "./src/worker.ts"`，`assets.directory = "./out"`，`assets.binding = "ASSETS"`；
4. `assets.not_found_handling = "404-page"`，因为模板是 Next 静态导出，不是 SPA；
5. 发布器用最终 origin 设置 `NEXT_PUBLIC_SITE_URL`，在服务器本地执行 `npm run build`；
6. 发布器使用 `npx wrangler deploy --config wrangler.jsonc` 上传 Worker 和静态资产；
7. 发布后必须执行线上首页、metadata、canonical、sitemap、robots、广告 API 和全部 loc/hreflang 直接 200 验证。

广告 API 不是纯静态文件。模板的 `src/worker.ts` 接管 `/api/ads/availability` 和 `/api/ads/<format>`，从 Worker vars 读取 8 个 `AD_*_B64`，其他请求交给 `env.ASSETS.fetch(request)`。

未提供 `siteUrl` 时，Factory 读取 Cloudflare account 的 workers.dev subdomain，使用 `https://<worker>.<subdomain>.workers.dev` 作为 `NEXT_PUBLIC_SITE_URL` 并自动验收。

提供正式域名时，Factory 会先用正式域名构建 canonical/sitemap，再部署到 workers.dev，并通过 Workers Custom Domains API 自动创建或复用该 hostname 到 Worker production 环境的绑定。只有 Cloudflare zone 缺失、API 权限不足、DNS 冲突或最终域名验收未通过时，回执才会保留 `hosting.status=awaiting_domain_configuration`；该状态不得声称正式域名已上线。问题处理后重试同一 Job，完成最终线上验收。

需要的凭据仍只保存在 factory 根 `.env` 或服务器 `factory.env`：

- `FACTORY_GITHUB_TOKEN`（本地也可复用 `gh auth login`）；
- `CLOUDFLARE_ACCOUNT_ID`；
- `CLOUDFLARE_API_TOKEN`，需要 Workers Scripts/Edit、Workers Routes/Custom Domains 相关权限，以及读取 workers.dev subdomain 的权限。

禁止为新站静默回退到 Cloudflare Pages、Vercel、Netlify 或 Docker 发布。
