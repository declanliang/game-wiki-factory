# 生产服务器部署记录与运维手册

本文记录当前单机生产环境的非敏感事实。它和 `docs/background-jobs.md` 一起使用；密钥、服务器地址、密码和 Token 不得写入本文。

空白服务器安装、全损恢复、备份与回滚的完整步骤见 `docs/bootstrap-from-github.md`；本文只记录当前生产约定和日常运维。

## 当前部署

- 系统：Ubuntu 24.04，systemd 托管。
- 应用：`/srv/game-wiki-factory/app`
- Python 虚拟环境：`/srv/game-wiki-factory/venv`
- SQLite、任务日志和配置快照：`/srv/game-wiki-factory/data`
- 游戏临时工作区：`/srv/game-wiki-factory/workspaces`
- 私有环境文件：`/srv/game-wiki-factory/secrets/factory.env`，权限 `0600`
- 安全命令入口：`/usr/local/bin/gamewiki`

`/usr/local/bin/gamewiki` 会先加载私有环境，再调用当前 Factory。SSH、计划任务和 OpenClaw 必须使用它；不要直接从应用目录运行 venv Python，否则会读到另一份默认 SQLite 数据库。

## 服务

```bash
sudo systemctl status gamewiki-worker gamewiki-control
sudo systemctl restart gamewiki-worker gamewiki-control
sudo journalctl -u gamewiki-worker -n 200 --no-pager
sudo systemctl list-timers gamewiki-cleanup.timer
```

- `gamewiki-worker`：默认并发领取两个游戏任务，同一时刻只允许一个 npm production build。
- `gamewiki-control`：仅监听 loopback，供本机控制面使用。
- `gamewiki-cleanup.timer`：按保留策略清理已经发布的临时工作区。
- `gamewiki-notifier.timer`：每2分钟消费持久化通知 outbox；不调用 LLM Agent。
- `gamewiki-supervisor.timer`：每分钟检查 checkpoint-safe 内容失败并冷却续跑；不调用 LLM Agent。
- 服务崩溃或服务器重启后，过期 lease 会被回收；流水线从磁盘 checkpoint 继续。

通知渠道配置完成后安装 timer：

```bash
sudo cp deploy/systemd/gamewiki-notifier.service deploy/systemd/gamewiki-notifier.timer /etc/systemd/system/
sudo cp deploy/systemd/gamewiki-supervisor.service deploy/systemd/gamewiki-supervisor.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gamewiki-notifier.timer gamewiki-supervisor.timer
```

发送失败时消息保持 pending 并退避，下一次 timer 继续尝试。

Supervisor 只执行 `docs/background-jobs.md` 中的确定性白名单策略。它不读取或修改密钥，不运行 Git 维护，不热改代码。自动恢复预算耗尽后，Notifier 才把异常交给用户/Codex。

成功发布后会立即删除可重建的 `node_modules/` 和 `.next/`，但保留源码、intake、调研 checkpoint 和日志到成功任务保留期结束。可用 `GAMEWIKI_PRUNE_SUCCESS_BUILD_ARTIFACTS=0` 临时关闭这一行为。

生产服务器当前磁盘使用率较高，因此它的私有环境把暂停领取阈值设为 90%。达到阈值时正在运行的任务不被粗暴终止，但 Worker 不再领取新任务。成功发布的源码以 GitHub Private repo 为长期存档，服务器工作区只是可删除的构建缓存。

## 提交和观察任务

配置文件放在服务器可读的非 Git 目录，然后执行：

```bash
/usr/local/bin/gamewiki jobs submit --config /path/to/game.json
/usr/local/bin/gamewiki jobs list --json
/usr/local/bin/gamewiki jobs status JOB_ID --json
/usr/local/bin/gamewiki jobs logs JOB_ID --tail 200
/usr/local/bin/gamewiki jobs retry JOB_ID
/usr/local/bin/gamewiki jobs cancel JOB_ID
```

所有未来游戏都使用新站配置。可以随基础信息提交手工关键词：

```json
{
  "schemaVersion": 3,
  "taskType": "site",
  "game": "Existing Game",
  "platform": "roblox",
  "officialUrl": "https://www.roblox.com/games/123/example",
  "siteUrl": "https://new-game.wiki",
  "manualKeywords": ["Existing Game codes", "Existing Game best units"],
  "publish": true
}
```

不要填写 repo、Cloudflare Pages project、`operation: rebuild`、`fullBuild` 或覆盖参数。同名 workspace/repo 已存在时任务应停止并交给维护者确认，不得自动替换。

## OpenClaw 专用 Agent

- Agent ID：`game-wiki-operator`
- Workspace：`/home/ubuntu/.openclaw/workspace-game-wiki-operator`
- 权限边界：只提交、查询、读日志、重试和取消；不读取环境文件、不在对话进程中执行长流水线、不把 repo 改成 Public。

在服务器测试或直接使用：

```bash
openclaw agent --local --agent game-wiki-operator --message \
  '请先实时查询任务队列，告诉我每个任务的阶段；不要启动前台流水线。'
```

自动化验收或脚本查询应附加一个新的 `--session-key agent:game-wiki-operator:ops-<日期或批次>`，避免复用很久以前的聊天上下文。实际聊天渠道可以保留自己的连续会话，但 Agent 仍必须每次执行实时 `jobs list --json`。

聊天渠道、收件人和通知命令属于服务器私有配置，不写入 Git。接手者只通过一次端到端测试确认：产生测试终态、渠道收到消息、ack 后 outbox 为空。不要从历史聊天推断当前绑定，也不要让 `game-wiki-operator` 抢占其他 Agent 的路由。

推荐提交 Prompt：

```text
请验证并提交我附带的 Game Wiki JSON；它包含游戏名、平台、官网、域名和新建/重建意图。
不要向我索要 repo 或 Cloudflare Pages project。提交后返回 job ID。
之后只查询后台任务，不要在对话里运行完整流水线；遇到 needs_attention 时返回首个失败阶段、日志路径、原因和建议动作。
```

## 凭据维护

服务器私有环境至少需要内容 API key 和 GitHub token。Factory 默认流程不运行广告 Job；在 Pages 自动化正式接入服务器前，Pages 项目、环境变量和部署由运营者在 Dashboard 手工完成。更新凭据后：

```bash
sudo chmod 600 /srv/game-wiki-factory/secrets/factory.env
sudo systemctl restart gamewiki-worker gamewiki-control
```

禁止把环境文件内容粘贴到 OpenClaw Prompt、GitHub Issue、日志或 AI 对话。

## Factory 更新流程

服务器地址、SSH 用户和私钥位置保存在团队的私有运维清单或本机 SSH config，不写入仓库。更新前先执行：

```bash
/usr/local/bin/gamewiki jobs list --json
cd /srv/game-wiki-factory/app
git status --short
git rev-parse HEAD
cp /srv/game-wiki-factory/data/jobs.sqlite3 /srv/game-wiki-factory/data/jobs.sqlite3.pre-update
```

必须确认无 `running` Job 且工作树干净。服务器配置了 Private GitHub deploy key 时：

```bash
git pull --ff-only
```

如果 remote 是 HTTPS 且服务器没有 GitHub 凭据，不要读取或临时打印 token。由已认证维护机创建增量 bundle：

```powershell
git fetch origin
git bundle create gamewiki-update.bundle main ^<SERVER_HEAD>
git bundle verify gamewiki-update.bundle
scp gamewiki-update.bundle <ssh-host>:/tmp/gamewiki-update.bundle
```

服务器只做快进：

```bash
cd /srv/game-wiki-factory/app
git fetch /tmp/gamewiki-update.bundle main
git merge --ff-only FETCH_HEAD
```

然后运行三套 Python 测试；模板或跨模块变更再运行模板脚本语法检查和 `npx tsc --noEmit`。测试通过后：

```bash
sudo systemctl restart gamewiki-worker gamewiki-control
sudo systemctl --no-pager --full status gamewiki-worker gamewiki-control
sudo systemctl list-timers 'gamewiki-*'
git rev-parse HEAD
/usr/local/bin/gamewiki jobs list --json
```

OpenClaw 的 workspace 指令如果变化，还要把 `deploy/openclaw/AGENTS.md`、`SOUL.md`、`TOOLS.md` 同步到 `/home/ubuntu/.openclaw/workspace-game-wiki-operator/`；仅更新 Factory Git checkout 不会自动更新这个独立 workspace。

## 生成与上线验收

每个成功任务必须同时满足：

1. 任务状态 `succeeded`，manifest 所有必需阶段完成。
2. Next.js production build 和本地站点检查通过。
3. GitHub repo 为 Private。
4. `result.hosting.provider=cloudflare-pages` 且 `status=manual_action_required`，并明确告知运营者后续步骤。

以上代表“生成完成”。要称为“上线完成”，还必须由运营者在 Cloudflare Pages 手工连接 Private GitHub、把构建输出设为 `out`、绑定域名、设置 `NEXT_PUBLIC_SITE_URL`、部署，并让 `npm run verify:deploy` 通过。canonical、sitemap、robots 不得包含 `example.com`；根路径必须 301 到 `/en`。Pages 部署成功本身不算线上验收。

## 2026-07-22 真实验收记录

| 游戏 | 平台 | Job ID | 内容产出 | 生产 QA | 发布结果 |
|---|---|---|---|---|---|
| Funnel Runners | Steam，本地 | `20260722T022228Z-funnel-runners-723a23` | 12 篇英文 + 60 篇翻译 | 120 loc / 840 hreflang 全部 200 | `succeeded`，按测试要求未发布 |
| Zenith Inc | Roblox，本地完整重建 + 内容 V5 增量 | `20260722T041610Z-zenith-inc-1d45c6` | 22 篇英文 + 110 篇翻译 | 204 loc / 1428 hreflang 全部 200 | 原 Private GitHub/Vercel 原地替换；7 个广告位验证通过 |
| Timebomb Duels | Roblox，服务器 | `20260722T023847Z-timebomb-duels-3a4676` | 6 篇英文 + 30 篇翻译 | 90 loc / 630 hreflang 全部 200 | Private GitHub + Vercel production |

线上验收：`https://zenith-inc-roblox.wiki/`、`https://timebomb-duels.wiki/`、各自 sitemap 和 robots 均返回 200；sitemap 不含 `example.com`。Zenith 的 7 个隔离广告路由返回 200 且精确代码哈希一致。OpenClaw 使用独立新 session 实时读取到了服务器任务 Job ID。

本次真实任务发现并修复了 Windows UTF-8 日志、随机验证端口、Next.js standalone 启动、默认语言根路径循环、旧 `.next/types`、Vercel token 进程参数、Git 提交作者关联、Vercel OIDC 临时文件和成功构建缓存占盘等问题。失败均停在 QA/发布边界，内容阶段通过 checkpoint 复用，没有重复调研与翻译。
