# 立即接手指南

本文是新维护者的第一入口。当前事实以代码、根目录 `release.json`、后台数据库和目标游戏的 `.gamewiki/manifest.json` 为准，不以聊天记录或历史设计文档为准。

## 1. 当前产品边界

- Factory 只支持 Roblox 和 Steam。
- 固定语言及顺序为 `en/es/de/fr/ja`。
- Factory 源码只在本仓库；游戏产物位于 Factory 同级的 `../<slug>/`，游戏目录本身就是 Next.js 根。
- 付费、可恢复状态在游戏根 `.gamewiki/`；最终可部署输入在 `intake/`。
- 后台站点任务默认完成 Private GitHub、Pages Direct Upload、`NEXT_PUBLIC_SITE_URL` 和部署。运营者只负责自定义域名绑定/DNS；正式域名尚未可达时状态为 `awaiting_domain_configuration`。
- 所有未来游戏都作为新项目从空 workspace 生产；不再接收 `operation: rebuild` 或旧 repo 覆盖输入。
- Factory 只接受站点生产 Job；广告转换和托管环境变量由独立广告 Agent 按 `docs/adsterra-environment-contract.md` 处理。

## 2. 接手顺序

1. 阅读 `README.md`、`AGENTS.md`、`docs/architecture.md`、`docs/runbook.md`。
2. 服务器/OpenClaw 工作再读 `docs/background-jobs.md`、`docs/openclaw-operator-guide.md` 和 `docs/server-deployment.md`。
3. 全新环境按 `docs/bootstrap-from-github.md` 恢复。
4. 查看目标子模块自己的 `AGENTS.md`。
5. 不读取、打印、复制或提交 `.env`/`factory.env` 的值。

`docs/design/` 和带日期的审计/验收记录用于解释历史决策，不是当前操作入口；与本指南或 runbook 冲突时，以当前代码和 runbook 为准。

## 3. 先确认代码一致

Windows 本地：

```powershell
git fetch origin
git status --short
git rev-parse HEAD
git rev-parse origin/main
```

服务器：

```bash
cd /srv/game-wiki-factory/app
git status --short
git rev-parse HEAD
```

三个提交号应一致。未跟踪的本地 bundle 不属于源码，不要误提交。服务器有运行任务时不得更新代码或重启 Worker。

## 4. 日常生产

长任务一律交给后台队列。输入可包含手工关键词：

```json
{
  "game": "Example Game",
  "platform": "roblox",
  "officialUrl": "https://www.roblox.com/games/123/example",
  "manualKeywords": [
    "Example Game codes",
    "Example Game best units",
    "Example Game progression guide"
  ],
  "publish": true
}
```

`manualKeywords` 最多 200 项；会规范化、去重并记录为 `user_provided`，但不会绕过证据和分类边界。

提交与查询：

```bash
/usr/local/bin/gamewiki jobs submit --config /private/path/game.json
/usr/local/bin/gamewiki jobs list --json
/usr/local/bin/gamewiki jobs status JOB_ID --json
/usr/local/bin/gamewiki jobs logs JOB_ID --tail 200
```

失败先读 status、manifest 和最新日志。普通网络、429、5xx、翻译缺项只重试原 Job：

```bash
/usr/local/bin/gamewiki jobs retry JOB_ID
```

不要新建同游戏替代任务，不要默认使用 refresh、recluster 或 overwrite。`quota_exhausted` 必须先充值或更换 key，再重试原 Job。

## 5. 两种“完成”

### 发布完成

站点 Job 可以在以下条件下标记 `succeeded`：

- 内容、五语言一致性、MDX、TypeScript 和 production build 通过；
- 新 GitHub 仓库已创建且为 Private；
- `result.hosting.provider` 为 `cloudflare-pages`，且 `result.hosting.status` 为 `complete` 或 `awaiting_domain_configuration`。

`complete` 可以说对应 origin 已部署并验证；`awaiting_domain_configuration` 只能说“Pages 已部署，等待正式域名绑定”。

### 上线完成

Factory 已创建 Direct Upload Pages 项目并部署。若状态为 `awaiting_domain_configuration`，运营者在该项目中：

1. 绑定最终域名；
2. 配置对应 DNS；`NEXT_PUBLIC_SITE_URL` 已由 Factory 设置，不要另建 Git-integrated 项目；
3. 在游戏根运行 `npm run verify:deploy`；
4. 确认首页 metadata、canonical、sitemap、robots 和全部 loc/hreflang 直接返回 200。

只有上述线上门通过，才能报告“已上线并验证”。

## 6. OpenClaw 边界

OpenClaw Agent `game-wiki-operator` 只负责提交、查询、日志、原 Job 重试和取消。它不得：

- 读取 secrets；
- 修改 Factory/游戏内容或数据库；
- 在聊天进程运行长流水线；
- 执行 Git 更新、服务重启或服务器热修；
- 把仓库改为 Public。

代码或内容质量问题保持 `needs_attention`，交给 Codex/维护者在本地修复、测试、推送，并在维护窗口部署。

## 7. 服务器维护窗口

更新前必须满足：队列无 `running` Job、数据库已备份、服务器工作树干净。标准顺序：

1. 本地完成修改和全部测试；
2. 提交并推送 GitHub；
3. 服务器 `git pull --ff-only`，或在服务器没有 Private GitHub 凭据时使用经过 `git bundle verify` 的 bundle 快进；
4. 服务器运行三套 Python 测试；
5. 重启受影响服务；
6. 验证提交号、服务状态、队列和 timer。

详细命令见 `docs/server-deployment.md`。

## 8. 最低验收

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -s pipeline\basic-info\tests -v
$env:PYTHONPATH=(Resolve-Path pipeline\guide-search).Path
python -m unittest discover -s pipeline\guide-search\tests -v
cd template
Get-ChildItem scripts -Filter '*.mjs' | ForEach-Object { node --check $_.FullName }
npx tsc --noEmit
```

跨模块契约变化还要执行至少一个真实 checkpoint 续跑或等价端到端验证，但不得为了测试无理由刷新付费阶段。
