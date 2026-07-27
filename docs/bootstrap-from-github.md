# 仅凭 GitHub 从零恢复 Game Wiki Factory

本文面向第一次接手的开发者或 AI。假设本地电脑和生产服务器都已丢失，只剩 Private GitHub 仓库、域名账户和单独备份的密钥。任何密钥都不得写入 Git、任务 JSON、Prompt 或日志。

## 先确认边界

- Factory 源码：`declanliang/game-wiki-factory`，包含调研、文章、翻译、模板、发布和后台任务系统。
- 每个已发布游戏是独立 Private GitHub repo，包含可部署源码、`intake/` 和五语言 `content/`。
- `.gamewiki/` 原始搜索、LLM 调试响应和 checkpoint 不进 Git。服务器完全丢失后，已发布网站可从游戏 repo 恢复，但未发布任务的中间 checkpoint 只有在另行备份时才能恢复。
- 生产密钥应存放在密码管理器或独立加密备份；GitHub 不是密钥备份。

## Windows 本地恢复

安装 Python 3.11+、Node.js 20–24、npm、Git、GitHub CLI 和 ffmpeg，然后：

```powershell
cd C:\Users\liang\Documents\Games
git clone https://github.com/declanliang/game-wiki-factory.git
cd game-wiki-factory
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cd template
npm ci
cd ..
Copy-Item .env.example .env
gh auth login
```

在 `.env` 中只填写实际使用的变量。内容流水线至少需要 ToAPIs/LLM key；搜索源按启用情况需要 DataForSEO、Serper、Jina；无人值守发布需要 `FACTORY_GITHUB_TOKEN`、`FACTORY_GITHUB_OWNER`、`CLOUDFLARE_ACCOUNT_ID` 和具有 Pages Edit 权限的 `CLOUDFLARE_API_TOKEN`。不要删除 `.env.example` 中未知变量，它是当前配置清单。

首次运行前执行：

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -s pipeline\basic-info\tests -v
$env:PYTHONPATH=(Resolve-Path pipeline\guide-search).Path
python -m unittest discover -s pipeline\guide-search\tests -v
cd template
Get-ChildItem scripts -Filter '*.mjs' | ForEach-Object { node --check $_.FullName }
npx tsc --noEmit
cd ..
```

先提交 `publish: false` 的测试任务，确认身份解析、日志和 checkpoint 目录正常；之后再提交真实发布任务。不要用 refresh 验证安装。

## 空白 Ubuntu 24.04 服务器恢复

以下命令中的仓库地址和系统用户可按实际环境调整。推荐保持目录契约不变：

```bash
sudo mkdir -p /srv/game-wiki-factory/{app,data,workspaces,secrets}
sudo chown -R ubuntu:ubuntu /srv/game-wiki-factory
git clone https://github.com/declanliang/game-wiki-factory.git /srv/game-wiki-factory/app
python3 -m venv /srv/game-wiki-factory/venv
/srv/game-wiki-factory/venv/bin/pip install --upgrade pip
/srv/game-wiki-factory/venv/bin/pip install -r /srv/game-wiki-factory/app/requirements.txt
cd /srv/game-wiki-factory/app/template && npm ci
```

系统还需 Node.js 20–24、npm、Git、`gh` 和 ffmpeg。Private clone 使用只读 deploy key 或最小权限 token；运行时 GitHub token 只授予创建/更新目标 Private repo 所需权限。

从 `.env.example` 创建 `/srv/game-wiki-factory/secrets/factory.env`，并至少设置：

```dotenv
GAMEWIKI_DATA_DIR=/srv/game-wiki-factory/data
GAMEWIKI_PROJECTS_ROOT=/srv/game-wiki-factory/workspaces
GAMEWIKI_DISK_PAUSE_PERCENT=90
GAMEWIKI_SUCCESS_RETENTION_HOURS=0
```

再填写 API、GitHub、通知渠道和随机生成的 `GAMEWIKI_CONTROL_TOKEN`。Cloudflare Pages 不需要服务器 token。设置权限：

```bash
sudo chown root:root /srv/game-wiki-factory/secrets/factory.env
sudo chmod 600 /srv/game-wiki-factory/secrets/factory.env
sudo cp /srv/game-wiki-factory/app/deploy/gamewiki-server /usr/local/bin/gamewiki
sudo chmod 755 /usr/local/bin/gamewiki
sudo cp /srv/game-wiki-factory/app/deploy/systemd/gamewiki-* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gamewiki-worker gamewiki-control
sudo systemctl enable --now gamewiki-notifier.timer gamewiki-supervisor.timer gamewiki-cleanup.timer
```

如果 Node 安装路径不同，先修改 `/usr/local/bin/gamewiki` 的 `PATH`。systemd 单元以 `ubuntu` 运行，因此 `data/`、`workspaces/` 和应用读取权限必须与之匹配。

## OpenClaw 恢复

创建专用 `game-wiki-operator` Agent 和 workspace，把 `deploy/openclaw/AGENTS.md`、`SOUL.md`、`TOOLS.md` 放入该 workspace。Agent 只能提交、查询、取消和按 runbook 重试任务；不能读取 secrets、修改 Factory 源码或在聊天进程运行长任务。

配置通知渠道时，将私有 argv JSON 写入 `GAMEWIKI_NOTIFICATION_COMMAND_JSON`，且恰有一个 `{message}` 占位符。Notifier 返回成功后才确认 outbox。API 额度/余额不足会立即进入 `needs_attention`，消息明确要求充值或更换 key，Supervisor 不会自动重试付费阶段。

## 健康检查与冒烟验收

```bash
/usr/local/bin/gamewiki jobs list --json
/usr/local/bin/gamewiki notifier --dry-run
/usr/local/bin/gamewiki supervisor --dry-run
sudo systemctl --no-pager --full status gamewiki-worker gamewiki-control
sudo systemctl list-timers 'gamewiki-*'
df -h / /srv/game-wiki-factory
```

在服务器执行根测试，再提交一个 `publish: false` 的测试游戏冒烟任务。另用临时 Private repo 和 Git-integrated Pages 项目验证 GitHub App repo 授权、API 权限、Production 环境变量、Cloudflare 服务端构建和线上 canonical/sitemap/robots/hreflang；测试资源验证后删除。正式自定义域名绑定/DNS仍是运营步骤。

## 更新、回滚与全损恢复

更新前确认没有 `running` 任务，备份 `data/jobs.sqlite3`，然后在 `app/` 执行 `git pull --ff-only`、安装依赖、跑测试，最后重启受影响服务。Private repo 应配置只读 deploy key；若服务器没有 GitHub 凭据，可由已认证维护机创建并验证 Git bundle，通过 SSH 传输后在服务器 `git fetch <bundle> main` 与 `git merge --ff-only FETCH_HEAD`。不要在服务器直接提交或热修。

回滚使用已知良好 commit：停止领取新任务，切到该 commit，重新安装锁定依赖、跑测试并重启。数据库 schema 变更前必须另存 SQLite 备份。

需要备份的生产资产：Factory Private repo、每个游戏 Private repo、域名/Cloudflare/GitHub 账户、服务器外的加密 secrets 备份，以及需要保留运营历史时的 `data/jobs.sqlite3`、任务配置和日志。不要备份或处理其他业务目录。

服务器全损后，按本文重建控制面；从各游戏 repo 可恢复线上源码。尚未发布任务如果没有外部 checkpoint 备份，只能重新提交并承担对应 API 成本。
