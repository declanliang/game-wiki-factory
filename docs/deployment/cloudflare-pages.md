# Git-integrated Cloudflare Pages 发布

Cloudflare Pages 是新任务的唯一托管平台。Factory 创建 Private GitHub 仓库，再创建连接该仓库 `main` 的 Pages 项目：

- Framework：Next.js 静态导出
- Build command：`npm run build`
- Output directory：`out`
- Production branch：`main`
- Production variable：`NEXT_PUBLIC_SITE_URL`

需要的 Factory 凭据只保存在本地 `.env` 或服务器 `factory.env`：

- `FACTORY_GITHUB_TOKEN`（本地也可复用 `gh auth login`）
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`，需要 Pages Edit 以及已授权的 GitHub App 仓库访问

未提供 `siteUrl` 时，Factory 使用项目的 `pages.dev` origin 并完成线上验收。提供正式域名但尚未绑定时，Pages 项目和环境变量仍会完成，Job 以 `awaiting_domain_configuration` 交给运营者；不得声称正式域名已经上线。

Pages 显示部署成功不代表验收结束。Factory 还必须验证 `/` 301 到 `/en`、全部 sitemap loc/hreflang 直接 200，以及全站 metadata、canonical、robots、内链和图片资源。

禁止静默回退到 Direct Upload、Vercel、Netlify 或 Docker 发布。
