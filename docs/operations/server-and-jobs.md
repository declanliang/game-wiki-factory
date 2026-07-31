# 服务器与后台队列速查

本文是生产命令速查；完整接手流程见 `../HANDOFF.md`。

## 常用命令

```bash
/usr/local/bin/gamewiki jobs submit --config /path/to/game.json
/usr/local/bin/gamewiki jobs submit-batch --config /path/to/batch.json
/usr/local/bin/gamewiki jobs list --json
/usr/local/bin/gamewiki jobs status JOB_ID --json
/usr/local/bin/gamewiki jobs logs JOB_ID --tail 200
/usr/local/bin/gamewiki jobs retry JOB_ID
/usr/local/bin/gamewiki jobs cancel JOB_ID
/usr/local/bin/gamewiki jobs notifications --json
/usr/local/bin/gamewiki jobs notifications --ack ID [...]
```

服务器/OpenClaw 必须使用 `/usr/local/bin/gamewiki`。不要直接运行 venv Python；那可能读到默认本地数据库而不是生产队列。

## 服务

```bash
sudo systemctl status gamewiki-worker gamewiki-control
sudo systemctl status gamewiki-agent2.timer gamewiki-supervisor.timer gamewiki-notifier.timer gamewiki-cleanup.timer
sudo journalctl -u gamewiki-worker -n 200 --no-pager
sudo journalctl -u gamewiki-agent2.service -n 120 --no-pager
sudo systemctl list-timers 'gamewiki-*'
```

- `gamewiki-worker`：执行站点生产和发布。
- `gamewiki-control`：本机控制 API。
- `gamewiki-notifier.timer`：投递通知 outbox。
- `gamewiki-supervisor.timer`：确定性恢复 checkpoint-safe 内容失败。
- `gamewiki-agent2.timer`：Codex CLI 受限修复单站内容/checkpoint 问题。
- `gamewiki-cleanup.timer`：清理过期 workspace 和可重建缓存。

## 状态含义

- `queued`：等待 Worker。
- `running`：Worker 已领取。
- `retry_wait`：可重试错误，等待冷却。
- `quota_wait`：供应商级额度/余额熔断，等待凭据恢复。
- `agent_repair`：Agent2 正在修复单站产物。
- `needs_attention`：需要维护者处理。
- `failed`：重试预算耗尽。
- `succeeded`：站点生产和要求的发布流程完成。
- `cancelled`：操作员取消。

## 维护窗口

更新 Factory 前：

```bash
/usr/local/bin/gamewiki jobs list --json
cd /srv/game-wiki-factory/app
git status --short
git rev-parse HEAD
cp /srv/game-wiki-factory/data/jobs.sqlite3 /srv/game-wiki-factory/data/jobs.sqlite3.pre-update
```

必须确认没有 `running` Job。更新后跑测试、重启受影响服务，再检查提交号、timer 和队列。

服务器无 GitHub 凭据时，用维护机创建并验证 git bundle，服务器只做 `git fetch <bundle> main` 与 fast-forward。

