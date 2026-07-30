# AI 接手与标准 Prompt

## 最小背景

这是一个混合确定性代码和 LLM 判断的 Roblox / Steam 攻略站工厂。AI 的职责不是手工逐步复制文件，而是运行统一入口、读取 manifest/log、修复通用问题并续跑。

如果本地或服务器不存在，先严格执行 `docs/bootstrap-from-github.md`，不要凭历史对话猜测目录、服务或密钥位置。

业务目标是为具体 Roblox 或 Steam 游戏生成信息型 Wiki。Factory 发布器在创建 Cloudflare Pages 站点时自动注入统一 shared ad profile 的 8 个 server-only 变量；Job/OpenClaw 不接收任意广告代码或覆盖配置。模板未获得有效变量时必须零渲染、零占位。合同见 `docs/advertising/adsterra-environment-contract.md`。

首页数据所有权：Basic Info 提供事实和深度文案；Guide Search 的缓存 YouTube 结果只可补一个严格匹配游戏的长视频；site-plan 决定可发布分类；现有文章提供具体内链和分类专题。模板不得反向发明事实、分类或文章。

内容深度 V4 把 Google 搜索需求与有证据的知识机会并列为发现来源。联网研究可以提出 Codes、Tier List、Updates 和具体实体页，但必须通过 URL 证据、置信度和 Basic Info 分类边界三重门槛。一个页面解决一个聚焦需求；Calculator 等工具页仍不在范围。完整设计见 `docs/design/content-depth-v4.md`。

## 标准执行 Prompt

```text
请在 C:\Users\liang\Documents\Games\game-wiki-factory 中，
为 PLATFORM（Roblox 或 Steam）游戏“GAME NAME”创建或续跑游戏 Wiki。

优先读取用户提供的 jobs/<game>.json 并执行：
python gamewiki.py --config jobs/<game>.json
如果没有配置文件，再使用直接参数模式。
目标目录：C:\Users\liang\Documents\Games\<game-slug>

约束：
- 先读工厂 README.md、AGENTS.md、docs/architecture.md、docs/runbook.md。
- 默认复用 checkpoint；不要主动使用 refresh/recluster/overwrite。
- 失败先读目标 `.gamewiki/manifest.json`、`configs/` 和最新日志。
- 优先修复工厂中的通用代码，再用同一命令续跑。
- 不打印或提交任何 .env/API key。
- 先确认 platform；Steam 身份使用 App ID，Roblox 身份使用 Place/Universe，不能混用事实字段。
- 所有游戏 GitHub 仓库只能是 Private；发布器不得创建 Public repo。
- 有正式域名时填写 `siteUrl`。后台任务自动发布 Private GitHub、创建连接该 repo `main` 的 Git-integrated Pages 项目、设置 `NEXT_PUBLIC_SITE_URL` 并触发 Cloudflare 构建部署；运营者只负责自定义域名绑定/DNS，禁止 `example.com` 出现在真实生产 sitemap/canonical。
- 不接纳完全无关主题，不为凑数量降低门槛；也不要把资料丰富的游戏强行压成 3–5 篇长文。
- 检查 Guide Search 的 page_opportunities 及审计结果；Codes、Tier List、Updates 和实体资料页必须保留其页面类型元数据。
- 不生成 Calculator、Planner、Team Builder 等工具页。
- 不手工补标签掩盖被截断的翻译。

生成发布标准：只保留有证据的 published 分类；简单游戏允许少量页面，资料丰富的游戏要保留不同意图和实体入口；Factory 新站只生成 en/es 且文章树一致；首次只公开 en，第三个自然日由 publication plan 公开 es；de/fr/ja 只由 Growth Agent 根据真实需求和用户批准扩展。intake、MDX、TypeScript、production build、Private GitHub 和 Pages 部署必须全部通过。正式域名未绑定时 `result.hosting.status=awaiting_domain_configuration`，不代表该域名已上线。

上线完成标准：Pages 部署后目标 origin 的根路径 301 到 `/en`，线上首页、metadata、sitemap、robots、所有 loc/hreflang 直接 200、self-canonical、OG 全部通过。自定义域名尚未绑定时，由运营者完成绑定/DNS后再执行最终域名验收。

最终报告：网站根目录、分类、语言、文章数、首页视频来源、manifest、最新日志、API 是否复用、Private repo、Pages project/deployment URL、hosting 状态，以及是否只剩域名绑定/DNS和最终验收。
```

用户可在配置中增加 `manualKeywords` 字符串数组。它们是补充发现源，仍必须通过风险过滤、证据门、Basic Info profile 和最终编辑门。多个游戏要求并发时使用监督器，不要自行开多个无协调终端：

```powershell
python gamewiki.py run-many "GAME A" "GAME B" --jobs 2
python gamewiki.py status
python gamewiki.py logs <slug> --tail 150
```

只有用户明确授权创建 GitHub/Cloudflare 外部资源时才运行 `python gamewiki.py publish <slug>`；该命令会创建 Git-integrated Pages 项目，域名绑定和 DNS 始终由运营者处理。

## 只做诊断的 Prompt

```text
请诊断 C:\Users\liang\Documents\Games\<game-slug> 最近一次 Game Wiki Factory 失败。
只读取 `.gamewiki/manifest.json` 和最新日志，说明第一个失败 stage、根因、是否需要 API 重做。
不要修改代码，不要使用 refresh/overwrite。
```

## 模板升级 Prompt

```text
请使用 C:\Users\liang\Documents\Games\game-wiki-factory 的最新模板升级
C:\Users\liang\Documents\Games\<game-slug>，保留 intake 和 `.gamewiki` checkpoint，
然后执行零成本续跑与完整 production 验收。
```

## 接手检查清单

1. 确认操作的是工厂源码还是某个游戏仓库。
2. 确认游戏根目录含 `package.json`、`intake/`、`.gamewiki/manifest.json`。
3. 读取 manifest 中 `currentAttempt.log`，不要猜测失败位置。
4. 统计已存在的英文和翻译文件，避免重复 API。
5. 修改跨模块契约时同步更新 schema、模板和测试。
6. 完成后报告验证证据，不只说“代码已改”。
7. 服务器/OpenClaw 接手时优先阅读 `docs/agents/openclaw-factory.md`，只通过后台队列控制长任务。
