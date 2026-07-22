# Game Wiki Factory 后台任务系统

本文是生产运行、故障恢复和 OpenClaw 对接的当前事实源。先阅读根目录 `README.md`、`docs/architecture.md`、`docs/runbook.md`，再阅读本文。

## 目标与边界

Factory 用同一条 `full_build` 流水线处理新站和旧站。旧站不是另一套内容升级逻辑：它重新执行最新的信息采集、关键词、页面规划、文章、翻译、模板、构建和 QA，仅复用指定 GitHub repo、Vercel project、域名及线上环境变量。发布前必须完成本地生产验收。

OpenClaw、命令行和未来管理界面只提交或控制任务；真正的长任务由独立 Worker 进程执行。关闭终端或 Agent 对话不得改变数据库中的任务状态，服务器重启后 Worker 可重新领取中断任务。

## 组件

```text
gamewiki.py jobs submit/status/logs/retry/cancel
                    │
                    ▼
          SQLite jobs.sqlite3
                    │
                    ▼
       gamewiki.py worker --concurrency N
                    │
                    ▼
      现有 gamewiki.py --config 流水线
                    │
                    ▼
 Basic → Search → SEO Scout → Template → QA → Publish
```

- SQLite 保存任务、attempt、状态和非敏感发布信息，不保存 API key。
- 每个任务使用独立 sibling workspace 和 `.gamewiki` checkpoint。
- Worker 通过原子 lease 防止两个进程领取同一任务。
- 流水线内部 checkpoint 仍是阶段恢复的事实源；任务数据库不复制内容产物。
- 日志写入 Factory runtime 目录，并继续保留游戏目录内的编排日志。

## 任务状态

- `queued`：等待 Worker。
- `running`：已获得 lease，后台进程运行中。
- `retry_wait`：可重试错误，等待 `available_at`。
- `needs_attention`：身份歧义、配置、余额、权限、schema/代码等不能安全自动处理的问题。
- `succeeded`：完整流程和要求的发布完成。
- `failed`：已超过自动重试上限。
- `cancelled`：操作员取消；Worker 在安全边界终止。

Worker 启动时会回收过期 lease。网络、429、5xx、连接重置等瞬时错误按 30 秒、120 秒、600 秒退避；身份歧义、认证/余额、配置、内容契约和构建代码错误进入 `needs_attention`，避免无意义重复付费。

## 配置契约

任务配置仍兼容 `jobs/example.json`，并增加可选发布目标：

```json
{
  "schemaVersion": 2,
  "game": "Example Game",
  "platform": "roblox",
  "officialUrl": "https://www.roblox.com/games/123/example",
  "publish": true,
  "fullBuild": true,
  "publication": {
    "githubOwner": "declanliang",
    "githubRepo": "example-game",
    "reuseExisting": true,
    "replaceRepositoryContents": true,
    "vercelProject": "example-game"
  }
}
```

`fullBuild: true` 强制刷新 Basic Info、关键词聚类和文章/翻译，是旧半成品升级和要求最新质量的新生产批次使用的模式。普通失败恢复不再次刷新；Worker 重试同一个 attempt 时依赖已落盘 checkpoint。

`replaceRepositoryContents: true` 表示旧 repo 的 tracked tree 由新站完整替换，不解决历史代码冲突。发布器先创建远端备份 tag，再以经过 QA 的新 `main` 覆盖远端；当前线上部署在新 Push 成功前不受影响。Repo 必须为 Private。

## 常用命令

```powershell
# 提交
python gamewiki.py jobs submit --config jobs\game.json

# 批量提交目录内 JSON
python gamewiki.py jobs submit-batch --config-dir jobs\batch

# Worker（前台调试）
python gamewiki.py worker --concurrency 2

# 查询
python gamewiki.py jobs list
python gamewiki.py jobs status <job-id>
python gamewiki.py jobs logs <job-id> --tail 200

# 恢复与控制
python gamewiki.py jobs retry <job-id>
python gamewiki.py jobs cancel <job-id>
```

服务器由 systemd/Docker restart policy 运行 Worker，不依赖 SSH 会话。
服务器 SSH 或 OpenClaw 中统一使用 `/usr/local/bin/gamewiki ...` 包装命令；它负责加载私有 EnvironmentFile。不要直接运行 venv Python，否则会连接默认本地数据库而不是生产队列。

## 密钥池

Factory 只读取根目录 `.env` 或系统环境变量。Serper/Jina 按编号发现非空 Key：

```dotenv
SERPER_API_KEY_1=
SERPER_API_KEY_2=
JINA_API_KEY_1=
JINA_API_KEY_2=
```

第一组额度不足、429/402/403 或明确 quota 错误后冷却/禁用该 slot，并切换下一组。日志只写 `keySlot`，禁止写 key。LLM 继续使用 `LLM_API_KEY_1..N`。服务器 secrets 由操作员直接写入私有 `.env`，不得进入 Git、OpenClaw Prompt 或日志。

## 存储与清理

- 成功任务：保留工作目录 72 小时；`.next`、`node_modules` 可立即清理。
- 失败/需处理任务：保留 14 天。
- manifest、任务数据库、配置快照和压缩日志长期保留。
- 磁盘达到 70% 告警，80% 暂停领取新任务，85% 优先清理已发布成功任务。
- GitHub Private repo 是成功网站源码的长期存档。

## OpenClaw 权限模型

专用 Agent 只能调用本机控制命令/API：提交、查询、日志、重试、取消。它不得读取 `.env`，不得把 repo 改 Public，不得绕过 QA 发布，不得因单阶段失败从头重复付费。未知异常进入 `needs_attention` 并汇报第一失败阶段、日志路径和建议动作。

## 验收

1. Worker 被终止后，lease 到期可恢复。
2. 同一 job 不会被两个 Worker 同时执行。
3. 发布失败不会重跑已完成内容阶段。
4. 临时错误有界重试，永久错误进入 `needs_attention`。
5. 新站创建 Private repo/Vercel；旧站复用目标并替换 repo 内容。
6. 未提供广告变量时零广告渲染；已有 Vercel 环境变量不被发布器删除。
