# AI / 开发者接手说明

先完整阅读 `README.md`、`docs/architecture.md`、`docs/runbook.md`、`docs/ai-handoff.md`。全新环境还必须阅读 `docs/bootstrap-from-github.md`，再查看目标子模块自己的 `AGENTS.md`。

## 不可破坏的约束

- 本仓库是唯一工厂源码；真实游戏产物只能写入工厂同级的 `../<slug>/`，游戏目录本身就是 Next.js 根。
- 最终部署输入必须在游戏根 `intake/`；调研、cache、manifest 和日志必须在游戏根 `.gamewiki/`。
- 所有模块只维护 factory 根目录 `.env`；不读取、打印、复制或提交其中的值。
- 模板支持语言为 `en/es/de/fr/ja`；Factory 新站默认生成语言严格为 `en/es`，初始只发布 `en`，第三个自然日发布 `es`。`de/fr/ja` 默认不生成，只能由飞书游戏管理员中的 Growth 专项职责根据真实搜索需求和用户批准扩展；不生成韩语。
- 当前平台范围严格为 Roblox 和 Steam。平台专属身份只在 Basic Info adapter 中处理，后续阶段消费统一事实契约；不得把 Steam App ID 当 Place ID，也不得把手柄支持写成 Steam Deck 官方认证。
- Basic Info 的 `game-profile.json` 定义分类候选边界；候选可宽于最终导航（最多 16），Guide Search 不能越界创建站点分类，site-plan 最终最多发布 8 类。
- `site-plan.json` 是 SEO Scout、intake 和模板的唯一语言/分类声明源。
- 只发布有证据的分类，最多 8 个；不为数量合成 fallback 主题。资料丰富的游戏应拆成多个不同意图或实体页面，不得继续用旧的 3–5 篇经验值过度合并。联网知识机会必须满足一个官方/创作者 URL 或两个不同支持 URL，并受 Basic Info profile 约束。
- 精确 Suggest 词不是联网知识机会的前提；有证据的系统、实体和不同玩家意图可以成为独立页面。每次 Guide Search 必须输出 `content-opportunity-report.json`，让小站能区分“信息稀少”和“门控淘汰”。
- Codes、Tier List、Updates 和实体资料页是当前支持的 MDX 形态；Calculator、Planner、Team Builder 等工具页不在本阶段范围。
- 正常续跑先验证 checkpoint，再跳过已完成工作。只有显式 refresh/overwrite 才重复付费调用。
- 每次外部命令都必须写独立日志，失败必须写 `manifest.json` 和 traceback。
- 生成的 GitHub 仓库必须且只能是 Private；不得提供 Public 发布参数。
- 今后所有游戏都作为新项目从头生产；新提交不得使用 `operation: rebuild`、`fullBuild` 或旧 repo 覆盖参数。默认托管平台只能是 Cloudflare Pages；历史 Vercel 站点保持不变。Factory 不接收或部署广告配置；模板广告变量契约只供独立广告 Agent 使用。
- 用户可在站点 JSON 中提供 `manualKeywords`。手工词是补充发现源，必须继续通过风险过滤、证据门、Basic Info profile 和最终编辑门，不能直接创造越界分类。
- 后台站点任务默认完成 Private GitHub、Git-integrated Cloudflare Pages、Production `NEXT_PUBLIC_SITE_URL` 和部署。新 Pages 项目必须连接该 Private GitHub repo 的 `main`，由 Cloudflare 执行 `npm run build` 并发布 `out`；不得静默回退到 Direct Upload。未提供正式域名时使用 `pages.dev` 并自动线上验收；提供但尚未绑定时以 `hosting.status=awaiting_domain_configuration` 交给运营者绑定域名，不能表述为“正式域名已上线”。
- Cloudflare Pages 显示部署成功不是上线验收完成。部署后必须验证 `/` 301 到 `/en`，并执行线上首页、metadata、canonical、sitemap、robots 和全部 loc/hreflang 直接 200 验证。

## 修改后最低验收

运行根、`pipeline/basic-info`、`pipeline/guide-search` 三套 Python 测试，模板运行 `node --check` 和 `npx tsc --noEmit`。修改跨模块契约时还必须做端到端验证；内容深度或模板结构变更优先使用两个信息形态不同的项目。
