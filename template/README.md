# Game Wiki 站点模板

这是 `game-wiki-factory` 内置的干净 Next.js Wiki 模板。编排器把模板同步到 `Games/<game-slug>/` 根目录；该目录本身就是可推送 GitHub、可部署 Cloudflare Pages 的网站项目。

模板同时支持 Roblox 与 Steam。平台差异已经由上游 Basic Info 转换为统一 intake 契约；模板不调用 Roblox/Steam API，也不根据平台自行猜测事实。

## 从工厂生成 Roblox / Steam 网站

命令必须在 `game-wiki-factory` 根目录执行，而不是在本模板或已经生成的网站目录中执行：

```powershell
cd C:\Users\liang\Documents\Games\game-wiki-factory
python gamewiki.py "Roblox Game" --platform roblox
python gamewiki.py "Steam Game" --platform steam --official-url "https://store.steampowered.com/app/<app-id>/<slug>/"
```

Steam 游戏建议始终提供官方商店 URL。游戏名可能重名、改名或与 DLC/Demo 相似，App ID 才是稳定身份。普通续跑重复同一条命令即可，默认复用 checkpoint；不要为了重试添加 `--refresh-basic`、`--recluster-keywords` 或 `--overwrite-articles`。

Steam 数据注意事项：

- 价格、评价数量和 Early Access 状态是采集时快照，未来可能变化。
- `full controller support` 不代表 Steam Deck Verified 或 Playable；没有官方等级时只能表述为未确认。
- Windows 系统要求不能自动推导 Linux/SteamOS 兼容性或具体帧率。
- Steam 官方 trailer、截图和 header 可作为媒体来源；第三方 YouTube 视频不得冒充官方频道。
- 网站部署只消费 `intake/`，Cloudflare Pages 不需要 Steam、搜索或 LLM API key。

## 唯一输入契约

```text
intake/
├─ site-identity.json
├─ site-content.json
├─ site-content.es.json
├─ site-content.de.json
├─ site-content.fr.json
├─ site-content.ja.json
├─ site-plan.json
├─ hero.<ext>
├─ favicon/
└─ articles/
   ├─ en/<category>/*.mdx
   ├─ es/<category>/*.mdx
   ├─ de/<category>/*.mdx
   ├─ fr/<category>/*.mdx
   ├─ ja/<category>/*.mdx
```

`site-plan.json` 是语言、分类、顺序和发布状态的唯一事实源。模板不会从 `content/en` 反推分类，也不会用正则修改 TypeScript 配置。五语言固定为 `en/es/de/fr/ja`。

## 生成站点

```powershell
npm ci
npm run launch:site
```

流水线依次执行：

1. 校验 intake、五语言和 published 分类。
2. 应用身份、首页文案和素材。
3. 清空生成的 `content/`，从 intake 幂等导入文章。
4. 将 intake site-plan 复制为 `src/config/site-plan.json`。
5. 从 site-plan 生成导航、分类标题、分类描述和语言配置。
6. 生成精选文章并运行 TypeScript、配置、生产构建验证。

调试时可跳过最终 build，但仍执行全部导入与契约检查：

```powershell
npm run launch:site -- --skip-build
```

## 常用检查

```powershell
npm run check:intake
npm run validate:articles
npm run check:config
npx tsc --noEmit
npm run build
```

## Adsterra 广告

广告是可选的模板运行时能力，不属于 Factory。独立广告 Agent 把已验证的完整 snippet 转成七个 server-only `AD_*_B64` 环境变量；变量名和转换规则见 Factory 的 `docs/adsterra-environment-contract.md`。

页面先调用 `/api/ads/availability` 获取运行时可用性，再按需挂载 `/api/ads/<format>` 同源沙箱 iframe。未配置或 Base64 无效时不会渲染 iframe、占位容器或空白间距。修改 Cloudflare Pages Production 变量后必须重新部署。

## Cloudflare Pages 部署

Factory 会通过 Pages API 创建连接 Private GitHub `main` 的项目，Root directory 留空，Build command 为 `npm run build`，Build output directory 为 `out`。Production 环境必须设置最终公开域名对应的 `NEXT_PUBLIC_SITE_URL`。部署后运行 `npm run verify:deploy`；根路径应 301 到 `/en`，而 sitemap 中的所有 loc/hreflang 必须直接返回 200。详细步骤见 `doc/Cloudflare-Pages部署指南.md`。

## 设计边界

- 本仓库不调用 LLM、不搜索、不翻译；上游必须提供成品。
- 平台来自 `site-content.json` 的 `site.gamePlatform`；模板不得把 Steam 强制写成 Roblox，反之亦然。
- `src/config/site-plan.json` 是生成文件，来源只能是 `intake/site-plan.json`。
- `content/` 是生成投影，每次 ingest 会先清空，防止旧游戏或已删除文章残留。
- site-plan 至少包含 1 个有真实关键词证据、最多 8 个 published 分类；不为数量生成 fallback 分类，每种语言必须交付相同文章树。
- `NEXT_PUBLIC_SITE_URL` 集中规范化：裸域名自动补 HTTPS，非法协议在构建前失败；`verify:deploy` 会检查线上 metadata、self-canonical 和 sitemap 直接 200，而不只检查首页 HTTP 200。
- 首页按“媒体入口 + 信息枢纽”组织：桌面 Hero 控制在约 576px，缩短页头后的留白，核心标题位于视觉中心、紧凑数据卡固定在内容下沿，保证常见首屏能立即看到主要信息；有可信视频时在首屏后展示点击加载的 YouTube；正文、分类和更新区使用受控宽度；专题卡片按三列从左到右排列，换行后从左侧继续；深度 section 使用醒目的无分割线编号卡片。Footer 的内容导航总标题统一为 `Wiki`，避免和其中的 Guides 分类重名。
- 分类标签和描述来自 site-plan 的五语言 `labels` / `descriptions`，模板只负责机械使用。
- 所有语言都使用显式前缀（`/en`、`/es`、`/de`、`/fr`、`/ja`），根 URL 301 到 `/en`；JSON-LD 和 sitemap 使用同一套路径。缺少译文时构建失败，不做英语回退。
- 具体游戏仓库必须提交 `intake/`；原始调研、cache 和日志位于被 Git 忽略的 `.gamewiki/`。
- 广告变量全部可选；环境变量未配置时页面保持原布局，不展示广告，也不预留空白。
