# Game Wiki Factory

输入一个 Roblox 游戏名，自动生成一个可直接推送 GitHub、部署 Vercel 的多语言攻略站。

这个仓库是唯一的“网站工厂”源码仓库，包含 Basic Info、Guide Search、SEO Scout、确定性规划契约和 Next.js 模板。具体游戏不会进入本仓库；默认生成到工厂同级目录，例如 `C:\Users\liang\Documents\Games\hellhole`。

## 一条命令

```powershell
cd C:\Users\liang\Documents\Games\game-wiki-factory
python gamewiki.py "GAME NAME"
```

第一次执行创建网站；同一命令再次执行会验证并复用 checkpoint。普通续跑不要加 refresh/overwrite 参数。

## 工厂目录

```text
game-wiki-factory/
├─ gamewiki.py                    对人友好的统一入口
├─ orchestrate_wiki.py            编排器实现
├─ project_contract.py            game profile / site plan 契约
├─ pipeline/
│  ├─ basic-info/                 身份、事实、首页、多语言配置、hero/favicon
│  ├─ guide-search/               Google Suggest 主词+a–z、搜索需求和语义聚类
│  └─ seo-scout/                  搜索、采集、文章、语义 QA、翻译
├─ template/                      干净 Next.js Wiki 模板
├─ schemas/                       跨阶段 JSON Schema
├─ tests/                         编排与契约测试
└─ docs/                          架构、运行、迁移和 AI 接手说明
```

## 生成的网站目录

```text
Games/<game-slug>/
├─ package.json                   Next.js/Vercel 项目根
├─ src/
├─ public/
├─ content/                       从 intake 生成的文章投影
├─ scripts/
├─ intake/                        最终输入的唯一事实源，应提交 Git
│  ├─ site-identity.json
│  ├─ site-plan.json
│  ├─ site-content.json
│  ├─ site-content.{es,de,fr,ja,ko}.json
│  ├─ hero.png
│  ├─ favicon/
│  └─ articles/{en,es,de,fr,ja,ko}/<category>/*.mdx
└─ .gamewiki/                     调研、cache、日志、manifest；默认不提交
   ├─ manifest.json
   ├─ basic-info/
   ├─ planning/
   ├─ content-pipeline/
   └─ logs/
```

网站根目录不再有额外的 `site/`。`intake/` 是最终可复现输入；`.gamewiki/` 是本地流水线状态。Vercel 不调用 LLM，也不需要搜索 API key。

## 首次安装

环境要求：

- Python 3.11+
- Node.js 20–24
- npm
- ffmpeg
- Git

```powershell
cd C:\Users\liang\Documents\Games\game-wiki-factory
python -m pip install -r requirements.txt
cd template
npm ci
cd ..
```

复制 `.env.example` 为 `.env`，只在本地填写密钥：

```powershell
Copy-Item .env.example .env
```

`.env` 被 Git 忽略，绝不会复制到游戏网站或日志。

## 正常执行与续跑

```powershell
python gamewiki.py "Hellhole"
```

默认输出：

```text
C:\Users\liang\Documents\Games\hellhole
```

自定义父目录：

```powershell
python gamewiki.py "Hellhole" --output-root D:\GameSites
```

每次执行会立即打印最新日志路径。主要状态位于：

```text
<game>/.gamewiki/manifest.json
<game>/.gamewiki/logs/orchestrator-<timestamp>.log
```

只有在明确需要产生新费用时才使用：

- `--refresh-basic`：重做 Basic Info 网络/LLM 任务。
- `--recluster-keywords`：保留原始搜索数据，重做语义聚类。
- `--overwrite-articles`：重做文章、QA 和翻译。

恢复失败的默认动作永远是“不加参数重新执行同一命令”。

## 数据和质量规则

- 固定语言：`en/es/de/fr/ja/ko`。
- Basic Info 生成 `game-profile.json`，定义分类语义边界。
- Guide Search 调用 Google Suggest 主词和 a–z，并从多个视频共同支持的稳定机制中召回补充主题；单个娱乐视频不能独立创建文章。
- `site-plan.json` 是分类、顺序、六语言标签、六语言分类描述和发布状态的唯一事实源。
- 不为分类数量合成关键词；通常争取 3–5 个可靠文章主题，证据稀少时接受更少，分类最多 8 个。
- `strategy/tips/tactics` 映射进 `guide`，但每个不同关键词仍生成独立文章。
- SEO Scout 在翻译前执行文不对题 QA。
- 翻译必须保留标题、列表、表格、FAQ 和 Callout 结构；截断响应不会成为 checkpoint。
- 六语言文章树必须完全一致。
- 最终验收包括 intake、TypeScript、配置、production build、sitemap 直接 200、self-canonical、OG 和 hreflang。

## 交给 AI 执行

把下面的 prompt 原样交给 Codex 或其他有本地终端权限的 AI，只替换游戏名：

```text
请在 C:\Users\liang\Documents\Games\game-wiki-factory 中，
为 Roblox 游戏“GAME NAME”创建或续跑游戏 Wiki。

执行：python gamewiki.py "GAME NAME"
目标目录：C:\Users\liang\Documents\Games\<game-slug>

要求：
1. 默认复用所有已经验证通过的 checkpoint。
2. 不要使用 refresh、recluster 或 overwrite，除非日志证明对应 checkpoint 无效。
3. 如果失败，先检查 <game>/.gamewiki/manifest.json 和最新日志，修复通用代码后用同一命令续跑。
4. 不允许为了通过 build 手工掩盖截断文章或降低相关性门槛。
5. 完成时必须确认：所有分类有真实关键词证据、六语言文章树一致、intake 通过、TypeScript 通过、production build 通过、sitemap loc/hreflang 全部直接 200、self-canonical 与 hreflang 完整。
6. 报告最终网站根目录、分类、语言、文章数、最新日志和任何部署前待配置项。
```

AI 接手前还应阅读：

- [`AGENTS.md`](AGENTS.md)
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/runbook.md`](docs/runbook.md)
- [`docs/ai-handoff.md`](docs/ai-handoff.md)

## 网站本地运行

```powershell
cd C:\Users\liang\Documents\Games\<game-slug>
npm ci
npm run dev
```

重新从 intake 物化并完成生产验收：

```powershell
npm run launch:site
```

## GitHub 与 Vercel

每个游戏目录是独立网站仓库：

```powershell
cd C:\Users\liang\Documents\Games\<game-slug>
git init
git add .
git commit -m "Initial game Wiki"
git remote add origin <GAME_REPO_URL>
git push -u origin main
```

在 Vercel 导入该仓库，Root Directory 留空。部署环境设置：

```text
NEXT_PUBLIC_SITE_URL=https://正式域名
```

模板会把误填的裸域名自动规范为 HTTPS，并统一去掉末尾路径和斜杠；Vercel 中仍建议填写完整 `https://...`。该变量是公开 canonical origin，不需要标记为 Sensitive（若团队策略强制则可保留）。

国际化页面使用 locale-aware URL 单一构造器：英语无 `/en` 前缀，其他语言 self-canonical；HTML、sitemap 和 JSON-LD 保持一致。根 URL 固定提供英语/x-default，不按请求头或 cookie 自动跳转。非英语消息或文章缺失会让验收失败，不会静默回退英语。

上线前运行：

```powershell
npm run verify:deploy
```

## 测试

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -s pipeline\basic-info\tests -v
$env:PYTHONPATH=(Resolve-Path pipeline\guide-search).Path
python -m unittest discover -s pipeline\guide-search\tests -v

cd template
npm ci
npx tsc --noEmit
```

不要把 `.env`、API key、`.gamewiki/cache`、`.gamewiki/logs`、`node_modules` 或 `.next` 提交 Git。
