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
- `CLOUDFLARE_API_TOKEN`，需要 Pages Edit 以及已授权的 GitHub App 仓库访问；若要自动创建新域名 CNAME，还需要对应 zone 的 DNS Read/Edit

未提供 `siteUrl` 时，Factory 使用项目的 `pages.dev` origin 并完成线上验收。提供正式域名时，Factory 会先做保守 DNS 预检：

- Cloudflare 账户中找得到 active zone，且 hostname 没有任何 DNS 记录：创建 proxied CNAME 指向 `<project>.pages.dev`，再请求 Pages Custom Domain。
- 已有 CNAME 指向同一个 Pages origin：复用并请求/轮询 Pages Custom Domain。
- 找不到 zone、zone 未激活、DNS API 无权限，或 hostname 已有 A/AAAA/CNAME/TXT 等记录但不是该 Pages origin：不覆盖、不删除、不请求新的 Pages Custom Domain，只把 `hosting.status` 置为 `awaiting_domain_configuration` 并写清 `customDomain.dns.nextAction`。

提供正式域名但 DNS/验证尚未完成时，Pages 项目、GitHub、环境变量和部署仍会完成，Job 以 `awaiting_domain_configuration` 交给运营者；不得声称正式域名已经上线。

Pages 显示部署成功不代表验收结束。Factory 还必须验证 `/` 301 到 `/en`、全部 sitemap loc/hreflang 直接 200，以及全站 metadata、canonical、robots、内链和图片资源。

禁止静默回退到 Direct Upload、Vercel、Netlify 或 Docker 发布。
