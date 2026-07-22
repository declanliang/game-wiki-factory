# Game Wiki Factory

输入一个 Roblox 或 Steam 游戏，自动完成游戏调研、关键词规划、文章生成、多语言翻译、Next.js Wiki 构建、GitHub 私有仓库发布和 Vercel production deployment。

固定语言为英语、西班牙语、德语、法语、日语和韩语。生成的网站位于 factory 同级目录，例如 `Games/hellhole/`。

## 首次安装

要求 Python 3.11+、Node.js 20–24、npm、Git、GitHub CLI、Vercel CLI 和 ffmpeg。

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
vercel login
```

无人值守或 GitHub Actions 使用 `.env`/Secrets 中的 `FACTORY_GITHUB_TOKEN` 和 `VERCEL_TOKEN`；本地没有 token 时自动复用上述 CLI 登录会话。

## 推荐执行方式：JSON 配置

复制示例文件：

```powershell
Copy-Item jobs\example.json jobs\my-game.json
```

## 后台批量生产

需要关闭终端后继续、每天排队多个站点或交给 OpenClaw 时，使用 SQLite Worker，不要让 Agent 会话承载长任务：

```powershell
python gamewiki.py jobs submit --config jobs\game.json
python gamewiki.py worker --concurrency 2
python gamewiki.py jobs list
python gamewiki.py jobs status <job-id>
python gamewiki.py jobs logs <job-id> --tail 200
python gamewiki.py jobs retry <job-id>
```

旧半成品也使用相同的 `fullBuild: true` 完整生产逻辑；`publication.replaceRepositoryContents: true` 会在创建远端备份 tag 后替换原 Private repo 的内容，并复用指定 Vercel project。完整状态机、服务器和 OpenClaw 说明见 [docs/background-jobs.md](docs/background-jobs.md)，实施计划见 [docs/design/background-production-v1.md](docs/design/background-production-v1.md)，换 AI 时使用 [docs/ai-takeover-background-worker.md](docs/ai-takeover-background-worker.md)。

Roblox 配置：

```json
{
  "schemaVersion": 1,
  "game": "Blox Monsters",
  "platform": "roblox",
  "officialUrl": "https://www.roblox.com/games/106763540857326/Blox-Monsters",
  "siteUrl": "https://blox-monsters-roblox.wiki",
  "publish": true,
  "refresh": {
    "basicInfo": false,
    "keywords": false,
    "articles": false
  }
}
```

Steam 配置：

```json
{
  "schemaVersion": 1,
  "game": "Funnel Runners",
  "platform": "steam",
  "officialUrl": "https://store.steampowered.com/app/3712080/Funnel_Runners/",
  "siteUrl": "https://funnelrunners.com",
  "publish": true,
  "refresh": {
    "basicInfo": false,
    "keywords": false,
    "articles": false
  }
}
```

执行：

```powershell
python gamewiki.py --config jobs\my-game.json
```

规则：

- `game`、`platform` 和 `officialUrl` 决定游戏身份。已知官方页面时必须填写，避免同名游戏误选。
- `platform` 只能是 `roblox`、`steam` 或 `auto`。
- `siteUrl` 可以是裸域名或完整 HTTPS URL；已知正式域名时填写。
- `publish: true` 会创建或更新 Private GitHub 仓库、Vercel 项目并执行 production deployment。
- `refresh` 默认全部为 `false`。普通续跑不要开启，防止重复 API 成本。
- 配置中的多余换行和连续空格会在执行前规范化，未知字段和拼写错误会直接报错。

`jobs/*.json` 默认不提交 Git，只提交 `jobs/example.json`。每次执行还会把当次配置快照和完整终端输出保存到游戏的 `.gamewiki/`，这些文件同样不会提交 Git。

```text
Games/<slug>/.gamewiki/configs/<timestamp>.json
Games/<slug>/.gamewiki/logs/<timestamp>-config.log
Games/<slug>/.gamewiki/logs/orchestrator-<timestamp>.log
Games/<slug>/.gamewiki/manifest.json
```

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
├─ intake/                 网站身份、首页内容、图片和六语言文章输入
├─ content/                网站实际读取的文章
├─ src/
├─ public/
├─ package.json
└─ .gamewiki/              本地调研、缓存、配置快照、日志和 manifest
```

GitHub 仅提交网站运行所需文件；`.gamewiki/`、`.env`、构建缓存和日志不会上传。游戏仓库只能创建为 Private。

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

未提供 `siteUrl` 时，线上 canonical、sitemap 和 robots 使用 Vercel production URL。提供 `siteUrl` 时，发布器先设置 Production 的 `NEXT_PUBLIC_SITE_URL`，再部署；仍需在 Vercel 添加正式域名并完成 DNS 配置。

## 可选 Adsterra 广告

每个网站使用自己申请的 Adsterra ad units。生成站点后，可把七段带标题的广告代码保存为站点根目录 `ad.txt` 并运行 `npm run ads:import`；脚本会自动校验和编码，不需要手工 Base64。也可以把原始代码直接粘贴到 Vercel 的 server-only `AD_*` 环境变量。所有广告变量均可留空，未配置时不会展示广告或保留空白。完整变量表和位置说明见生成站点的 `README.md`。

旧半成品升级时应通过后台配置设置 `fullBuild: true`，让它按当前标准重新调研、规划、生成和翻译；失败后的同一任务重试会自动改用 checkpoint，不会再次支付已经完成阶段的 API 成本。不要为旧站维护第二套升级流水线。

## 出错时交给 AI

不需要粘贴完整日志。提供游戏名或项目目录，并使用下面的提示词：

```text
请检查并继续完成游戏“GAME NAME”。

读取该项目 .gamewiki/manifest.json、configs 和最新 logs。
已完成的 Basic Info、关键词、文章和翻译不要重新生成。
修复实际问题后从 checkpoint 继续，使用最新版 factory 模板。
GitHub 仓库必须为 Private，并完成 Vercel production deployment。
最后检查 canonical、sitemap、robots 和 hreflang。
```

## 代码结构

```text
game-wiki-factory/
├─ gamewiki.py             统一入口
├─ factory_cli.py          配置、批量、状态和日志命令
├─ orchestrate_wiki.py     主流水线
├─ project_contract.py     跨阶段内容契约
├─ publisher.py            GitHub/Vercel 发布
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
