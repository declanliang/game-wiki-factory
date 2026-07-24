# Game Wiki Factory

输入一个 Roblox 或 Steam 游戏，自动完成游戏调研、关键词规划、文章生成、多语言翻译、Next.js Wiki 构建，并发布到 GitHub Private 仓库。新游戏使用 Cloudflare Pages；仓库连接、域名和环境变量由站点运营者手动完成。历史站点继续保留原 Vercel 部署，不在新任务中重建或迁移。

第一次接手先读 [立即接手指南](docs/takeover.md)。全新电脑或服务器仅凭 GitHub 恢复时，再按 [从零恢复手册](docs/bootstrap-from-github.md) 操作。当前生产风险见 [生产就绪审计](docs/production-readiness-audit-2026-07-23.md)。

固定语言为英语、西班牙语、德语、法语和日语。生成的网站位于 factory 同级目录，例如 `Games/hellhole/`。

## 首次安装

要求 Python 3.11+、Node.js 20–24、npm、Git、GitHub CLI 和 ffmpeg。

```powershell
cd C:\Users\liang\Documents\Games\game-wiki-factory
python -m pip install -r requirements.txt
cd template
npm ci
cd ..
Copy-Item .env.example .env
```

只维护 factory 根目录的 `.env`：

```text
game-wiki-factory/.env
```

Basic Info、Guide Search、SEO Scout 和发布器都会从这里读取配置。`.env` 被 Git 忽略，不会复制到游戏项目、日志或 GitHub。需要本地发布时先登录一次：

```powershell
gh auth login
```

无人值守或 GitHub Actions 使用 `.env`/Secrets 中的 `FACTORY_GITHUB_TOKEN`；本地没有 token 时自动复用上述 GitHub CLI 登录会话。Cloudflare Pages 连接与配置在 Dashboard 手工完成，不向 Factory 提供 Cloudflare token。

## 推荐执行方式：JSON 配置

复制示例文件：

```powershell
Copy-Item jobs\example.json jobs\my-game.json
```

外部收集的关键词可直接放进配置的 `manualKeywords` 数组，无需创建 Guide Search 源码目录下的手工文件。示例见 `jobs/example.json`。

## 后台批量生产

需要关闭终端后继续、每天排队多个站点或交给 OpenClaw 时，使用 SQLite Worker，不要让 Agent 会话承载长任务：

```powershell
python gamewiki.py jobs submit --config jobs\game.json
python gamewiki.py worker --concurrency 2
python gamewiki.py jobs list
python gamewiki.py jobs notifications --json
python gamewiki.py notifier --once
python gamewiki.py supervisor --once
python gamewiki.py jobs status <job-id>
python gamewiki.py jobs logs <job-id> --tail 200
python gamewiki.py jobs retry <job-id>
```

一次提交多个游戏：

```powershell
Copy-Item jobs\batch.example.json jobs\daily.json
python gamewiki.py jobs submit-batch --config jobs\daily.json
```

今后所有游戏都按新项目从空 workspace 开始生产，不再接受旧站 `rebuild` 输入。失败恢复只重试原 Job 并复用它自己的 checkpoint。完整状态机、服务器和 OpenClaw 说明见 [docs/background-jobs.md](docs/background-jobs.md)。

成功、最终失败、取消和 `needs_attention` 会进入持久化通知 outbox；渠道成功送达后再用 `jobs notifications --ack ...` 确认。Agent 只负责队列控制和 runbook 内的常规恢复，任何核心代码或生产逻辑问题必须升级给 Codex/基础设施维护者，禁止直接热修服务器工作树。

服务器可通过 `GAMEWIKI_NOTIFICATION_COMMAND_JSON` 配置渠道发送命令，并定时执行 `gamewiki.py notifier --once`。Dispatcher 只在发送命令返回成功后确认消息；发送失败会保留并指数退避，不需要让聊天 Agent 常驻或反复消耗 LLM。

服务器的 Supervisor 每分钟检查一次失败事件。只有文章生成/翻译明确保存了有效 checkpoint、且失败属于可继续的内容阶段时，才自动冷却并恢复同一个 Job；默认最多 6 轮。身份、密钥/余额、schema、代码、构建、GitHub/Vercel 安全问题不会自动处理，最终才通知用户和 Codex。这样批量任务不依赖 OpenClaw 对话持续在线。

当前稳定生产版本由根目录 `release.json` 固定，普通 Git commit 不改变版本。认证规则和已上线站点清单见 [docs/releases/v1_0722.md](docs/releases/v1_0722.md)。

首页采用任务优先的信息架构，并支持有证据的 Codes/Update 等“当前无结果”状态页；网站本身即 Wiki，不生成 `/wiki/` 分类。设计与验收边界见 [docs/design/task-first-home-and-status-pages.md](docs/design/task-first-home-and-status-pages.md)。

Roblox 配置：

```json
{
  "game": "Blox Monsters",
  "platform": "roblox",
  "officialUrl": "https://www.roblox.com/games/106763540857326/Blox-Monsters",
  "siteUrl": "https://blox-monsters-roblox.wiki",
  "publish": true
}
```

Steam 配置：

```json
{
  "game": "Funnel Runners",
  "platform": "steam",
  "officialUrl": "https://store.steampowered.com/app/3712080/Funnel_Runners/",
  "siteUrl": "https://funnelrunners.com",
  "publish": true
}
```

单站配置不必填写 `schemaVersion`、`taskType` 或 `operation`，系统会自动规范为新的站点任务。可以用 `manualKeywords` 随游戏基础信息提交外部收集的关键词。

执行：

```powershell
python gamewiki.py --config jobs\my-game.json
```

规则：

- 只有 `game` 必填；已知 `platform`、`officialUrl` 和正式域名时应同时填写，减少歧义和人工介入。
- `platform` 只能是 `roblox`、`steam` 或 `auto`。
- `siteUrl` 可以是裸域名或完整 HTTPS URL；已知正式域名时填写。
- `manualKeywords` 是可选字符串数组，最多 200 项；系统会清理空白、按大小写去重，并作为 `user_provided` 来源进入 Guide Search。它们仍受风险过滤、证据门和 Basic Info 分类边界约束。
- `publish: true` 会创建新的 Private GitHub 仓库，随后任务即可标记成功。回执会标记 `hosting.provider=cloudflare-pages` 和 `hosting.status=manual_action_required`，提示运营者在 Cloudflare Pages 连接仓库、把构建输出设为 `out`、配置域名和 `NEXT_PUBLIC_SITE_URL` 后手动部署。
- 日常配置不需要 GitHub repo 或托管平台项目名。每个游戏都创建新的 Private GitHub repo。
- `refresh` 默认全部为 `false`。普通续跑不要开启，防止重复 API 成本。
- 配置中的多余换行和连续空格会在执行前规范化，未知字段和拼写错误会直接报错。

`jobs/*.json` 默认不提交 Git，只提交文件名以 `.example.json` 结尾的示例。每次执行还会把当次配置快照和完整终端输出保存到游戏的 `.gamewiki/`，这些文件同样不会提交 Git。

```text
Games/<slug>/.gamewiki/configs/<timestamp>.json
Games/<slug>/.gamewiki/logs/<timestamp>-config.log
Games/<slug>/.gamewiki/logs/orchestrator-<timestamp>.log
Games/<slug>/.gamewiki/manifest.json
```

Guide Search 还会生成 `.gamewiki/planning/guide-search/content-opportunity-report.json`，记录数据源返回量、研究机会数、入选页面、实体覆盖和拒绝原因。看到文章少时，先用它判断是公开资料确实少，还是机会在证据/编辑门被合并或拒绝。

OpenClaw 的标准 JSON、指令和完成汇报契约见 [docs/openclaw-operator-guide.md](docs/openclaw-operator-guide.md)。日常只提交游戏资料或广告 JSON，不要让 Agent 在聊天进程内运行长流水线。

## 命令行兼容方式

不使用配置文件时仍可执行：

```powershell
python gamewiki.py "GAME NAME" --platform roblox --official-url "ROBLOX URL"
python gamewiki.py "GAME NAME" --platform steam --official-url "STEAM STORE URL"
python gamewiki.py "GAME NAME" --platform roblox --official-url "ROBLOX URL" --site-url "https://game.example" --publish
```

长命令必须保持游戏名引号在同一行。日常生产推荐使用 JSON 配置，避免 PowerShell 换行和转义问题。

## 续跑与日志

同一游戏再次执行相同配置，会验证并复用已有 checkpoint。默认不会重复生成已经完成的 Basic Info、关键词、文章和翻译。

```powershell
python gamewiki.py --config jobs\my-game.json
python gamewiki.py status
python gamewiki.py status <game-slug>
python gamewiki.py logs <game-slug> --tail 200
python gamewiki.py resume <game-slug>
```

仅在明确需要重新付费调研或生成时修改：

```json
"refresh": {
  "basicInfo": true,
  "keywords": true,
  "articles": true
}
```

- `basicInfo`：忽略基础信息缓存并重新调研。
- `keywords`：复用原始搜索数据，重新聚类和规划。
- `articles`：覆盖文章并重新生成、QA、翻译。

某一步失败时，首先保持三个值为 `false`，直接重跑相同配置。

## 多游戏并发

```powershell
python gamewiki.py run-many "Game A" "Game B" --jobs 2
```

需要固定平台和官方 URL 时，使用 UTF-8 TSV，每行格式为：

```text
游戏名<TAB>平台<TAB>官方 URL
```

```powershell
python gamewiki.py run-many --games-file .\games.tsv --jobs 2 --publish
```

批量日志和 manifest 位于：

```text
game-wiki-factory/.gamewiki/runs/<run-id>/
```

## 生成结果

每个游戏目录都是可独立推送和部署的 Next.js 项目：

```text
Games/<game-slug>/
├─ intake/                 网站身份、首页内容、图片和五语言文章输入
├─ content/                网站实际读取的文章
├─ src/
├─ public/
├─ package.json
└─ .gamewiki/              本地调研、缓存、配置快照、日志和 manifest
```

GitHub 提交网站运行所需文件以及成本最高的最终产物 `intake/`、五语言 `content/`；`.gamewiki/`、`.env`、原始搜索/LLM 调试缓存、构建缓存和日志不会上传。完整 `.gamewiki/` 不适合 Git 历史；未来若需要跨服务器保存原始调研 checkpoint，应使用带生命周期的私有对象存储。游戏仓库只能创建为 Private。

## 本地预览与上线检查

```powershell
cd C:\Users\liang\Documents\Games\<game-slug>
npm run dev
```

生产检查：

```powershell
npm run build
npm run verify:deploy
```

后台站点任务不会自动部署 Cloudflare Pages。运营者连接 Private repo，设置 Build command 为 `npm run build`、Build output directory 为 `out`，绑定域名并把 Production 的 `NEXT_PUBLIC_SITE_URL` 设为最终公开 origin；随后部署并执行 `npm run verify:deploy`。未完成这一步时，Job 的 `succeeded` 只代表生成、构建、QA 和 Private GitHub 完成，不代表网站已上线。

## 可选 Adsterra 广告

每个网站使用自己申请的 Adsterra ad units。在目标游戏仓库把平台返回的原始 JSON 保存为不会提交的 `ad.txt`，然后本地校验和转换：

```powershell
Set-Location ..\<game-slug>
npm run ads:import
```

Factory 默认的 Cloudflare Pages 流程暂不接受后台 `taskType: ads`：Cloudflare 的环境变量和部署仍由运营者在 Dashboard 手工完成。先用 `npm run ads:import` 校验并转换配置，再把对应 `AD_*_B64` Secret 逐项写入 Pages Production 环境；部署后逐个验证 `/api/ads/<format>`。不得把广告原始代码写入 Git 或日志。

广告可以晚于网站生产单独配置，不会重跑内容。变量全部留空时，不会渲染广告 iframe、占位或空白。Adsterra 素材实际填充可能仍受平台同步延迟影响。

失败后的同一任务重试自动复用 checkpoint，不会重复已经完成的付费阶段。不要为同一个失败任务创建替代 Job。

## 出错时交给 AI

不需要粘贴完整日志。提供游戏名或项目目录，并使用下面的提示词：

```text
请检查并继续完成游戏“GAME NAME”。

读取该项目 .gamewiki/manifest.json、configs 和最新 logs。
已完成的 Basic Info、关键词、文章和翻译不要重新生成。
修复实际问题后从 checkpoint 继续，使用最新版 factory 模板。
GitHub 仓库必须为 Private。后台任务完成后，明确汇报 Cloudflare Pages 仍需手工连接仓库、设置 `out`、域名、`NEXT_PUBLIC_SITE_URL`、部署和线上验收。
最后检查 canonical、sitemap、robots 和 hreflang。
```

## 代码结构

```text
game-wiki-factory/
├─ gamewiki.py             统一入口
├─ factory_cli.py          配置、批量、状态和日志命令
├─ orchestrate_wiki.py     主流水线
├─ project_contract.py     跨阶段内容契约
├─ publisher.py            Private GitHub 发布与托管平台回执
├─ adsterra.py             广告 JSON 校验（Cloudflare 环境变量需手工配置）
├─ jobs/example.json       游戏配置示例
├─ pipeline/
│  ├─ basic-info/
│  ├─ guide-search/
│  └─ seo-scout/
├─ template/               Next.js Wiki 模板
├─ schemas/
├─ tests/
└─ docs/
```

跨模块约束和维护说明见 `AGENTS.md`、`docs/architecture.md`、`docs/runbook.md` 和 `docs/ai-handoff.md`。

## 测试

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -s pipeline\basic-info\tests -v
$env:PYTHONPATH=(Resolve-Path pipeline\guide-search).Path
python -m unittest discover -s pipeline\guide-search\tests -v

cd template
Get-ChildItem scripts -Filter '*.mjs' | ForEach-Object { node --check $_.FullName }
npx tsc --noEmit
```

`npm run check:config` 和 `npm run build` 面向已经导入具体游戏 intake 的生成项目；干净模板没有 published 内容，不能单独通过内容同步检查。
