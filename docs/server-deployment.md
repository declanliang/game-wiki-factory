# 生产服务器部署记录与运维手册

本文记录当前单机生产环境的非敏感事实。它和 `docs/background-jobs.md` 一起使用；密钥、服务器地址、密码和 Token 不得写入本文。

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
- 服务崩溃或服务器重启后，过期 lease 会被回收；流水线从磁盘 checkpoint 继续。

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

新站和旧站都使用同一个配置契约。旧站设置：

```json
{
  "fullBuild": true,
  "publish": true,
  "publication": {
    "githubOwner": "declanliang",
    "githubRepo": "existing-private-repo",
    "reuseExisting": true,
    "replaceRepositoryContents": true,
    "vercelProject": "existing-vercel-project"
  }
}
```

发布器会先创建 `pre-rebuild-<UTC>` 远端备份 tag，再用已通过 build/QA 的新站替换 `main`；Vercel 项目、正式域名和已有环境变量会被复用而不是删除。

## OpenClaw 专用 Agent

- Agent ID：`game-wiki-operator`
- Workspace：`/home/ubuntu/.openclaw/workspace-game-wiki-operator`
- 权限边界：只提交、查询、读日志、重试和取消；不读取环境文件、不在对话进程中执行长流水线、不把 repo 改成 Public。

在服务器测试或直接使用：

```bash
openclaw agent --local --agent game-wiki-operator --message \
  '请先实时查询任务队列，告诉我每个任务的阶段；不要启动前台流水线。'
```

尚未给 Agent 绑定聊天渠道，这是有意的：绑定错误会抢占现有 OpenClaw 渠道路由。需要从微信、飞书或其他渠道下达任务时，应先决定专用账号/路由，再只把该路由绑定给 `game-wiki-operator`。

推荐提交 Prompt：

```text
请为“GAME NAME”提交完整后台任务。
平台：roblox 或 steam
官方页面：https://...
这是：新站 / 旧站完整重建
GitHub Private repo：owner/repo
Vercel project：project-name

提交后返回 job ID。之后只查询后台任务，不要在对话里运行完整流水线；遇到 needs_attention 时返回首个失败阶段、日志路径、原因和建议动作。
```

## 凭据维护

服务器私有环境至少需要内容 API key、GitHub token 和 Vercel token。推荐使用可撤销的专用生产 Token，不依赖个人电脑 CLI 的临时登录缓存。更新凭据后：

```bash
sudo chmod 600 /srv/game-wiki-factory/secrets/factory.env
sudo systemctl restart gamewiki-worker gamewiki-control
```

禁止把环境文件内容粘贴到 OpenClaw Prompt、GitHub Issue、日志或 AI 对话。

## 发布验收

每个成功任务必须同时满足：

1. 任务状态 `succeeded`，manifest 所有必需阶段完成。
2. Next.js production build 和部署检查通过。
3. GitHub repo 为 Private；旧站有本次重建前的备份 tag。
4. Vercel production deployment 成功并关联指定项目。
5. canonical、sitemap、robots 不包含 `example.com`。
6. 未配置广告变量时页面不渲染广告；发布过程不删除已有广告或域名环境变量。
