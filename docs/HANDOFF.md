# Game Wiki Factory 接手手册

这是本仓库当前唯一的接手主文档。新维护者先读根目录 `README.md`、`AGENTS.md` 和本文；只在需要具体合同细节时再打开 `docs/contracts/`、`docs/advertising/`、`docs/deployment/`、`docs/agents/`。

当前事实以代码、`release.json`、后台 SQLite、目标游戏 `.gamewiki/manifest.json` 和本文件为准。历史讨论、旧版本设计稿和聊天记录不作为操作手册。

## 1. 项目边界

- Factory 只支持 Roblox 和 Steam。
- 所有未来游戏都作为新项目从空 workspace 创建；不再处理 `operation: rebuild`、`fullBuild` 或旧 repo 覆盖。
- Factory 源码只在本仓库；真实游戏产物写入 Factory 同级的 `../<slug>/`，游戏目录本身就是 Next.js 根。
- 最终部署输入在游戏根 `intake/`；调研、cache、manifest 和日志在游戏根 `.gamewiki/`。
- 新站默认只生成 `en/es`；首发只公开 `en`，第三个自然日自动公开 `es`。`de/fr/ja` 只由 Growth 专项根据真实搜索需求和用户批准扩展；不生成韩语。
- 默认发布到 Cloudflare Workers Static Assets，不再新增 Cloudflare Pages 或 Vercel 项目。
- 每个游戏创建自己的 Private GitHub repo。禁止创建或改成 Public。
- Factory 只负责站点生产和发布；广告代码采集/转换不属于主流程。发布器只从 `config/ads/animal-hospital-profile.json` 自动配置固定 shared ad profile。

## 2. 核心流水线

```text
site/job JSON
  → Basic Info：Roblox/Steam 官方身份、事实、首页、图片、语言和分类候选
  → Guide Search：Suggest/DataForSEO/联网证据、manualKeywords、机会审计
  → site-plan：最多 8 个有证据分类，声明页面意图和语言
  → SEO Scout：搜索、采集、英文文章、QA、西语翻译
  → intake/content：物化网站输入和文章树
  → template：Next.js 静态站点、metadata、sitemap、hreflang、广告 API
  → publisher：Private GitHub + Workers Static Assets + 线上验收
```

`site-plan.json` 是语言、分类和发布页面的唯一声明源。Basic Info 的 `game-profile.json` 定义分类候选边界；Guide Search 不能越界发明分类。资料少的游戏允许页面少；资料丰富的游戏应拆成多个不同玩家意图或实体页，不为凑数量合成 fallback 主题。

支持的内容形态是 Codes、Tier List、Updates、Entity 和 Guide。Calculator、Planner、Team Builder 等工具页不在当前范围。

## 3. 日常提交

推荐只通过后台队列提交长任务：

```bash
/usr/local/bin/gamewiki jobs submit --config /path/to/game.json
/usr/local/bin/gamewiki jobs submit-batch --config /path/to/batch.json
/usr/local/bin/gamewiki jobs list --json
/usr/local/bin/gamewiki jobs status JOB_ID --json
/usr/local/bin/gamewiki jobs logs JOB_ID --tail 200
```

单站输入：

```json
{
  "game": "Example Game",
  "platform": "roblox",
  "officialUrl": "https://www.roblox.com/games/123/example",
  "siteUrl": "https://example-game.wiki",
  "manualKeywords": ["Example Game codes", "Example Game best units"],
  "publish": true
}
```

规则：

- `platform` 只能是 `roblox`、`steam` 或 `auto`。
- `officialUrl` 已知时必须填写，避免身份歧义；Steam 用 Store App URL，Roblox 用 Experience URL。
- `siteUrl` 可省略；省略时使用 `workers.dev` 并自动验收。
- `manualKeywords` 最多 200 项，是补充发现源，仍受风险过滤、证据门、Basic Info profile 和最终编辑门约束。
- 不填写 GitHub repo、Cloudflare Pages/Workers project、广告变量或旧 rebuild 参数。

## 4. 失败恢复

默认原则：重试原 Job，复用 checkpoint，不新建替代 Job，不主动 refresh/recluster/overwrite。

```bash
/usr/local/bin/gamewiki jobs retry JOB_ID
/usr/local/bin/gamewiki jobs cancel JOB_ID
/usr/local/bin/gamewiki jobs notifications --json
/usr/local/bin/gamewiki jobs notifications --ack ID [...]
```

先看：

1. `jobs status JOB_ID --json`
2. `jobs logs JOB_ID --tail 200`
3. 游戏 `.gamewiki/manifest.json`
4. 最新 `orchestrator-*.log`
5. 对应 Basic Info / Guide Search / SEO Scout / site / publish 日志

可以安全重试的典型情况：

- 网络、429、5xx、连接重置；
- 文章/翻译阶段已有有效 checkpoint，剩余部分失败；
- Cloudflare/GitHub transient publish 但发布输入未损坏。

需要人类或维护者处理：

- 平台身份歧义、官方 URL 错误；
- API key、余额、供应商模型路由、权限；
- schema、核心代码、模板/发布器 bug；
- DNS/custom domain 验证；
- secret 扫描、GitHub repo 可见性异常。

额度/余额类错误由供应商级熔断处理：首条告警必须说明 API、端点和非敏感凭据组；其他任务进入 `quota_wait`，不要逐个重试。修复凭据后只重试首条 Job，系统会统一恢复暂停任务。

## 5. 后台组件和 Agent2

服务器使用 systemd：

- `gamewiki-worker`：领取站点任务，默认并发 2，build 并发 1。
- `gamewiki-control`：本机 loopback 控制 API。
- `gamewiki-notifier.timer`：投递持久化通知。
- `gamewiki-supervisor.timer`：确定性恢复 checkpoint-safe 内容失败，不调用 LLM。
- `gamewiki-agent2.timer`：每 5 分钟调用 Codex CLI 做受限单站修复。
- `gamewiki-cleanup.timer`：清理可重建缓存和过期 workspace。

Agent2 只能修单个游戏 workspace/checkpoint：MDX、metadata、重复 title/description、翻译格式化、slug/checkpoint 投影、明确 transient publish。它不能读取或打印 secrets，不能改 Factory 源码，不能 push GitHub，不能调用 Cloudflare/GitHub 发布，不能执行 `jobs retry`。修好后只把原 Job 放回 `retry_wait`，后续由 Worker 续跑和发布。

API key、余额、模型路由、DNS、权限、schema 和核心代码问题必须升级给本地 Codex/维护者。

## 6. 发布和上线验收

发布器默认完成：

- 创建或复用 Private GitHub repo；
- 使用 Private GitHub repo 保存站点源码；
- 生成本地 `wrangler.jsonc`，设置 `NEXT_PUBLIC_SITE_URL` 和 shared ad profile 的 8 个 server-only `AD_*_B64` Worker vars；
- 在服务器本地用最终 origin 执行 `npm run build`，输出 `out`；
- 使用 `wrangler deploy` 发布 Workers Static Assets；
- 自动验证部署。

提供 `siteUrl` 时，发布器会用该正式域名构建 canonical/sitemap，部署到 `workers.dev`，并自动创建或复用 Workers custom domain/route。只有 zone、权限、DNS 冲突或最终域名验收未通过时，Job 才以 `awaiting_domain_configuration` 明确交接，不能声称正式域名已上线。

`result.hosting.status`：

- `complete`：目标 origin 已通过线上首页、metadata、canonical、robots、sitemap、hreflang、广告 API 验收。
- `awaiting_domain_configuration`：Workers Static Assets、GitHub、Worker vars 和 workers.dev 部署已完成，但正式域名仍有 zone、权限、DNS、custom domain 或验证问题；不能说正式域名已上线。

Workers 控制台显示成功不等于 Factory 验收完成。必须验证 `/` 301 到 `/en`、广告 API，且 sitemap 内所有 loc/hreflang 直接 200。

## 7. 本地开发与验证

首次安装：

```powershell
cd C:\Users\liang\Documents\Games
git clone https://github.com/declanliang/game-wiki-factory.git
cd game-wiki-factory
python -m pip install -r requirements.txt
cd template
npm ci
cd ..
Copy-Item .env.example .env
```

只维护 Factory 根目录 `.env`。不要复制、打印或提交其中的值。

最低验收：

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -s pipeline\basic-info\tests -v
$env:PYTHONPATH=(Resolve-Path pipeline\guide-search).Path
python -m unittest discover -s pipeline\guide-search\tests -v
cd template
Get-ChildItem scripts -Filter '*.mjs' | ForEach-Object { node --check $_.FullName }
npx tsc --noEmit
```

跨模块契约变化还要做端到端 checkpoint 续跑或等价验证；不要为了测试无理由刷新付费阶段。

## 8. 服务器更新

更新前必须确认无 `running` Job，备份 SQLite，服务器工作树干净。

```bash
/usr/local/bin/gamewiki jobs list --json
cd /srv/game-wiki-factory/app
git status --short
git rev-parse HEAD
cp /srv/game-wiki-factory/data/jobs.sqlite3 /srv/game-wiki-factory/data/jobs.sqlite3.pre-update
```

优先：

```bash
git pull --ff-only
```

服务器无 GitHub 凭据时，用维护机创建 bundle：

```powershell
git fetch origin
git bundle create gamewiki-update.bundle main ^<SERVER_HEAD>
git bundle verify gamewiki-update.bundle
scp gamewiki-update.bundle <host>:/tmp/gamewiki-update.bundle
```

服务器只做快进：

```bash
cd /srv/game-wiki-factory/app
git fetch /tmp/gamewiki-update.bundle main
git merge --ff-only FETCH_HEAD
```

然后跑测试，重启受影响服务，检查 timer 和队列。OpenClaw workspace 是独立目录；`deploy/openclaw/AGENTS.md`、`SOUL.md`、`TOOLS.md` 变化时要另行同步到 `/home/ubuntu/.openclaw/workspace-game-wiki-operator/`。

## 9. 从零恢复

空白服务器目录约定：

```text
/srv/game-wiki-factory/app          Factory Git checkout
/srv/game-wiki-factory/venv         Python venv
/srv/game-wiki-factory/data         SQLite、任务日志、通知 outbox
/srv/game-wiki-factory/workspaces   游戏工作区
/srv/game-wiki-factory/secrets      私有 factory.env
/usr/local/bin/gamewiki             安全命令入口，负责加载 factory.env
```

安装后：

```bash
sudo mkdir -p /srv/game-wiki-factory/{app,data,workspaces,secrets}
sudo chown -R ubuntu:ubuntu /srv/game-wiki-factory
git clone https://github.com/declanliang/game-wiki-factory.git /srv/game-wiki-factory/app
python3 -m venv /srv/game-wiki-factory/venv
/srv/game-wiki-factory/venv/bin/pip install -r /srv/game-wiki-factory/app/requirements.txt
cd /srv/game-wiki-factory/app/template && npm ci
```

从 `.env.example` 创建 `/srv/game-wiki-factory/secrets/factory.env`，至少设置：

```dotenv
GAMEWIKI_DATA_DIR=/srv/game-wiki-factory/data
GAMEWIKI_PROJECTS_ROOT=/srv/game-wiki-factory/workspaces
GAMEWIKI_DISK_PAUSE_PERCENT=90
GAMEWIKI_SUCCESS_RETENTION_HOURS=0
```

再填内容 API、搜索 API、GitHub、Cloudflare、通知和 Agent2 认证。设置：

```bash
sudo chown root:root /srv/game-wiki-factory/secrets/factory.env
sudo chmod 600 /srv/game-wiki-factory/secrets/factory.env
sudo cp /srv/game-wiki-factory/app/deploy/gamewiki-server /usr/local/bin/gamewiki
sudo chmod 755 /usr/local/bin/gamewiki
sudo cp /srv/game-wiki-factory/app/deploy/systemd/gamewiki-* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gamewiki-worker gamewiki-control
sudo systemctl enable --now gamewiki-notifier.timer gamewiki-supervisor.timer gamewiki-agent2.timer gamewiki-cleanup.timer
```

健康检查：

```bash
/usr/local/bin/gamewiki jobs list --json
/usr/local/bin/gamewiki notifier --dry-run
/usr/local/bin/gamewiki supervisor --dry-run
/usr/local/bin/gamewiki agent2 --dry-run --once
sudo systemctl --no-pager --full status gamewiki-worker gamewiki-control
sudo systemctl list-timers 'gamewiki-*'
df -h / /srv/game-wiki-factory
```

## 10. OpenClaw 和 Growth 边界

OpenClaw `game-wiki-operator` 是传令兵，只能提交、查询、日志、重试、取消和通知 ack。它不得读取 secrets、修改源码、重启服务、提交 Git、运行前台流水线或绕过 QA。

Growth 职责由飞书账号 `cli_aad59e06a3fa5bee` 绑定的现有游戏管理员承担。它只在站点上线后读取 GSC/GSA 数据，提出关键词和语言扩展方案；用户批准后只修改单个游戏 repo，不改 Factory、不碰广告、不改 Cloudflare 环境变量。

详细对话格式见：

- `docs/agents/openclaw-factory.md`
- `docs/agents/growth-agent.md`
