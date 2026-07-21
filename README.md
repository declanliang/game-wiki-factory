# Game Wiki Factory

输入一个 Roblox 或 Steam 游戏名，自动生成一个可直接推送 GitHub、部署 Vercel 的多语言攻略站。当前产品范围只覆盖这两个平台。

这个仓库是唯一的“网站工厂”源码仓库，包含 Basic Info、Guide Search、SEO Scout、确定性规划契约和 Next.js 模板。具体游戏不会进入本仓库；默认生成到工厂同级目录，例如 `C:\Users\liang\Documents\Games\hellhole`。

## 一条命令

```powershell
cd C:\Users\liang\Documents\Games\game-wiki-factory
python gamewiki.py "GAME NAME"
```

同名游戏或 Steam 游戏建议显式指定平台。Steam 最好同时提供官方商店 URL，以 App ID 确定身份：

```powershell
python gamewiki.py "Funnel Runners" --platform steam --official-url "https://store.steampowered.com/app/3712080/Funnel_Runners/"
python gamewiki.py "Hellhole" --platform roblox
python gamewiki.py "Hellhole" --platform roblox --site-url hell-hole-roblox.wiki --publish
```

不指定 `--platform` 时会先尝试 Roblox、再尝试 Steam；身份存在歧义时流水线会停止，不会猜测。

### Steam 命令行特别注意

- 推荐同时传 `--platform steam` 和完整的 Steam Store App URL；稳定身份是 URL 中的数字 App ID，不是标题或 slug。
- 在 factory 根目录执行命令。生成结果仍位于同级 `Games/<game-slug>/`，该目录就是 Next.js/Vercel 项目根。
- 失败后用完全相同的命令续跑。默认会复用已完成的搜索、生成和翻译，不会重复付费。
- `--refresh-basic`、`--recluster-keywords`、`--overwrite-articles` 都可能产生新 API 费用，只有日志证明 checkpoint 无效时才使用。
- Steam 价格、评价和 Early Access 是采集快照；完整手柄支持不能写成 Steam Deck Verified/Playable。
- 如果只有游戏名而没有官方 URL，可以使用 `auto`，但同名游戏、Demo、DLC 或名称过于通用时应停止并补充官方 URL。

第一次执行创建网站；同一命令再次执行会验证并复用 checkpoint。普通续跑不要加 refresh/overwrite 参数。

同时处理两到三个游戏：

```powershell
python gamewiki.py run-many "Game A" "Game B" --jobs 2
```

批量任务需要为每个游戏固定官方身份时，使用 UTF-8 TSV 清单；每行是 `游戏名<TAB>平台<TAB>官方 URL`：

```text
Blox Monsters	roblox	https://www.roblox.com/games/106763540857326/Blox-Monsters
Funnel Runners	steam	https://store.steampowered.com/app/3712080/Funnel_Runners/
```

```powershell
python gamewiki.py run-many --games-file .\games.tsv --jobs 2 --publish
```

旧的一行一个游戏名格式仍然支持。TSV 模式会把每个 URL 传入对应子进程，同时继续共享 LLM/key/build 并发限制。

该命令为每个游戏启动隔离进程，并在所有进程之间统一限制 LLM 总并发、单 key 并发和 Next.js 构建并发。增加 `LLM_API_KEY_2`、`LLM_API_KEY_3` 后会自动按编号发现，不要求编号连续。

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

无需翻找目录即可查看状态和日志：

```powershell
python gamewiki.py status
python gamewiki.py status <game-slug>
python gamewiki.py logs <game-slug> --tail 150
python gamewiki.py resume <game-slug>
```

多游戏运行清单和独立控制台日志位于 `game-wiki-factory/.gamewiki/runs/<run-id>/`。

## 数据和质量规则

- 固定语言：`en/es/de/fr/ja/ko`。
- Basic Info 生成 `game-profile.json`，定义分类语义边界。候选边界可最多包含 16 类，最终 `site-plan` 仍最多发布 8 类，避免在关键词证据出现前过早丢掉真实类别。
- Basic Info 还可生成 2–4 个证据支持的 `home.guideSections`，为首页补充核心玩法、入门路径、成长和关键系统；模板只会把其中属于已发布 `site-plan` 分类的条目解析成链接。
- Guide Search 调用 Google Suggest 主词和 a–z，并把去重后的视频标题+URL交给联网背景研究；同一命名实体被至少两个不同视频支持时，可召回独立角色/单位/模式/物品页。联网研究还会发现有证据的 Codes、Tier List 和 Updates 页面机会。单个娱乐视频不能独立创建文章。
- 首页视频优先使用 Basic Info 已确认的 trailer；没有时只复用 Guide Search 已缓存的 YouTube 结果，选择标题完整匹配游戏名、平台语义一致、时长 2–60 分钟的最高排名长视频。选中结果只填充视频 ID，不把第三方频道冒充官方频道，也不新增 API 调用。
- `site-plan.json` 是分类、顺序、六语言标签、六语言分类描述和发布状态的唯一事实源。
- 不为分类或文章数量合成主题；页面机会必须有一个官方/创作者来源 URL，或至少两个不同的支持 URL，并且仍受 Basic Info 分类边界约束。简单游戏可以只有少量页面，资料丰富的游戏应拆成更多可独立搜索和互链的聚焦页面；分类最多 8 个。
- 当前重点页面形态包括 Codes、Tier List、Updates、实体资料页和既有攻略页；Calculator、Planner、Team Builder 等工具页暂不生成。
- 首页使用游戏 Hero 作为沉浸式背景，并从已发布文章确定性生成分类专题入口；专题至少需要两篇真实文章，不创建空区块或虚假链接。
- `strategy/tips/tactics` 映射进 `guide`，但每个不同关键词仍生成独立文章。
- SEO Scout 在翻译前执行文不对题 QA。
- 翻译必须保留标题、列表、表格、FAQ 和 Callout 结构；截断响应不会成为 checkpoint。
- 英文生成单独限制为 10,000 completion tokens；截断重试会自动改用紧凑、无表格的降级提示词，避免重复字符耗尽预算。
- 翻译仅有标题或描述超限时会本地压缩 SERP 字段并重新验证正文，不会为元数据小问题重翻整篇文章。
- 不同英文页面若被翻译成相同的泛化标题，流水线会保留译文并按英文主题 slug 追加短限定词，避免多篇页面拥有重复 SEO 标题。
- 六语言文章树必须完全一致。
- 增量重聚类保留 SEO Scout 的历史文章 checkpoint，但最终 `intake/articles` 只投影当前 site-plan 的 published 分类；被计划淘汰的旧分类不会泄漏到网站。
- 最终验收包括 intake、TypeScript、配置、production build、sitemap 直接 200、self-canonical、OG 和 hreflang。

## 交给 AI 执行

把下面的 prompt 原样交给 Codex 或其他有本地终端权限的 AI，只替换游戏名：

```text
请在 C:\Users\liang\Documents\Games\game-wiki-factory 中，
为 PLATFORM（Roblox 或 Steam）游戏“GAME NAME”创建或续跑游戏 Wiki。

执行：python gamewiki.py "GAME NAME" --platform PLATFORM
如果是 Steam 且已知商店页，再加：--official-url "STEAM URL"
目标目录：C:\Users\liang\Documents\Games\<game-slug>

要求：
1. 默认复用所有已经验证通过的 checkpoint。
2. 不要使用 refresh、recluster 或 overwrite，除非日志证明对应 checkpoint 无效。
3. 如果失败，先检查 <game>/.gamewiki/manifest.json 和最新日志，修复通用代码后用同一命令续跑。
4. 不允许为了通过 build 手工掩盖截断文章或降低相关性门槛。
5. 完成时必须确认：所有分类有真实关键词证据、六语言文章树一致、intake 通过、TypeScript 通过、production build 通过、sitemap loc/hreflang 全部直接 200、self-canonical 与 hreflang 完整。
6. 报告最终网站根目录、分类、语言、文章数、最新日志和任何部署前待配置项。
7. 只有用户明确要求发布时才创建外部资源；GitHub repo 必须且只能是 Private。
8. 若已提供正式域名，使用 `--site-url` 让发布器配置 `NEXT_PUBLIC_SITE_URL`；未提供时站点回退到 Vercel 自动域名，不允许 `example.com` 上线。
```

AI 接手前还应阅读：

- [`AGENTS.md`](AGENTS.md)
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/runbook.md`](docs/runbook.md)
- [`docs/ai-handoff.md`](docs/ai-handoff.md)
- [`docs/design/content-depth-v4.md`](docs/design/content-depth-v4.md)

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
cd C:\Users\liang\Documents\Games\game-wiki-factory
python gamewiki.py publish <game-slug>
```

也可以在生成命令后直接发布：`python gamewiki.py "GAME NAME" --publish`；批量生产使用 `python gamewiki.py run-many "Game A" "Game B" --jobs 2 --publish`。

发布命令要求项目流水线状态为 `complete`，先检查敏感文件，再幂等创建/更新 GitHub repo，并创建或复用同名 Vercel 项目。**游戏 GitHub 仓库只能是 Private**：创建固定使用私有模式，已有仓库也会在推送前后验证 `PRIVATE` 可见性，不提供 Public 开关。GitHub 使用 `FACTORY_GITHUB_TOKEN`（或 `GH_TOKEN`）；Vercel 优先使用 `VERCEL_TOKEN`，本地未设置 token 时可复用已登录的 Vercel CLI。

未传 `--site-url` 时，发布器不写 Vercel 环境变量，模板会使用 Vercel 自动提供的 production URL，避免 sitemap、robots 和 canonical 出现 `example.com`。若创建项目时已经知道正式域名，可运行 `python gamewiki.py "GAME" --site-url game.example --publish`，或 `python gamewiki.py publish <slug> --site-url game.example`；发布器会把规范化后的 HTTPS origin 写入 Production 的 `NEXT_PUBLIC_SITE_URL`。绑定域名并部署后执行 `npm run verify:deploy`。只推 GitHub 时加 `--skip-vercel`。回执写入 `.gamewiki/publish.json`，不含 token。

仓库内的 `.github/workflows/generate-and-publish.yml` 支持手动输入游戏名 JSON 数组，并以最多 3 个矩阵任务并发生成、建仓和导入 Vercel。

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
