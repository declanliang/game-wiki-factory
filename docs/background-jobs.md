# Game Wiki Factory 后台任务系统

本文是生产运行、故障恢复和 OpenClaw 对接的当前事实源。先阅读根目录 `README.md`、`docs/architecture.md`、`docs/runbook.md`，再阅读本文。

## 目标与边界

Factory 只接收新站任务。每个游戏从空 workspace 执行信息采集、关键词、页面规划、文章、翻译、模板、构建和 QA，并创建自己的 Private GitHub repo 与 Git-integrated Cloudflare Pages 项目。GitHub 发布前必须完成本地生产验收。

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
- 成功时把文章/分类数量、Private repo、Pages project/deployment 和域名交接状态写入 `result_json`；`jobs status --json` 会返回为 `result`，因此 workspace 清理后 OpenClaw 仍能准确汇报发布结果。
- 每个任务使用独立 sibling workspace 和 `.gamewiki` checkpoint。
- Worker 通过原子 lease 防止两个进程领取同一任务。
- 流水线内部 checkpoint 仍是阶段恢复的事实源；任务数据库不复制内容产物。
- 日志写入 Factory runtime 目录，并继续保留游戏目录内的编排日志。

## 任务状态

- `queued`：等待 Worker。
- `running`：已获得 lease，后台进程运行中。
- `retry_wait`：可重试错误，等待 `available_at`。
- `needs_attention`：身份歧义、配置、余额、权限、schema/代码等不能安全自动处理的问题。

API quota/credit/balance 耗尽会记录为 `quota_exhausted` 原因并立即进入 `needs_attention`：不消费普通重试次数、不由 Supervisor 恢复，Notifier 首条消息会明确要求充值或更换 key。恢复后只重试同一 Job ID，以复用已经落盘的 checkpoint。

## 事件驱动自动恢复

`gamewiki-supervisor.timer` 每分钟运行一次确定性策略，不调用 LLM。它只恢复异常文本明确承诺“已保存有效 checkpoint”的内容阶段失败：

- 英文文章部分生成成功，剩余文章因上游 API 暂时失败；
- 多语言翻译部分成功，剩余翻译因上游 API 暂时失败。

同一个 Job 冷却后进入 `retry_wait`，下一次继续跳过已有文章、QA verdict 和翻译文件。默认最多自动恢复 6 次。自动恢复发生后，对应的临时终态通知会被抑制；最终成功正常通知，超过恢复预算仍失败才发送 `needs_attention/failed`。

以下问题永不自动恢复：身份或官网歧义、API Key/余额/权限、schema、代码和构建错误、GitHub/Cloudflare 安全问题、Secret 扫描失败。它们必须保持终态并升级给基础设施维护者。

```bash
/usr/local/bin/gamewiki supervisor --once
/srv/game-wiki-factory/venv/bin/python gamewiki.py supervisor --dry-run
```

相关环境变量：

- `GAMEWIKI_SUPERVISOR_MAX_RECOVERIES=6`
- `GAMEWIKI_SUPERVISOR_COOLDOWN_SECONDS=300`
- `GAMEWIKI_DISK_PAUSE_PERCENT=90`

Supervisor 在磁盘达到暂停阈值时不会恢复任务。

## Checkpoint 保留边界

每个 Private 网站仓库已跟踪最终、可部署且成本最高的产物：`intake/` 与五语言 `content/`。不要把整个 `.gamewiki/` 提交到 Git：原始搜索页、视频转录、LLM 调试响应和二进制归档会快速膨胀 Git 历史，也可能包含不适合长期复制的第三方上下文。

运行中的断点续跑依赖服务器 workspace；发布成功后 GitHub 是网站源码的长期存档。若未来确实需要跨服务器恢复原始调研 checkpoint，应使用带生命周期和访问控制的对象存储，并在 Factory 中记录对象哈希；不要使用 Git/LFS 充当任务缓存。
- `succeeded`：完整流程和要求的发布完成。
- `failed`：已超过自动重试上限。
- `cancelled`：操作员取消；Worker 在安全边界终止。

Worker 启动时会回收过期 lease。网络、429、5xx、连接重置等瞬时错误按 30 秒、120 秒、600 秒退避；身份歧义、认证/余额、配置、内容契约和构建代码错误进入 `needs_attention`，避免无意义重复付费。

终态 `succeeded`、`failed`、`needs_attention`、`cancelled` 会原子写入 notification outbox。读取不等于送达，只有渠道成功发送后才能 acknowledge，因此轮询和 Agent 重启不会造成消息永久丢失：

```bash
python gamewiki.py jobs notifications --json
python gamewiki.py jobs notifications --ack 12 13
```

通知 outbox 是渠道无关的基础设施。OpenClaw、微信、飞书等具体渠道通过短周期 cron 或独立 dispatcher 消费它；未配置渠道时不会发送，也不会伪造成功通知。

推荐生产方式是让 cron 每 2 分钟执行一次确定性 dispatcher，而不是唤醒 LLM Agent：

```bash
/usr/local/bin/gamewiki notifier --once
```

`GAMEWIKI_NOTIFICATION_COMMAND_JSON` 是 argv JSON，其中必须有一个 `{message}` 占位符。发送命令返回0才 acknowledge；失败保留 pending 并按30秒到30分钟指数退避。具体账号和收件人只放服务器私有环境，不进入 Git。

## 配置契约

站点任务只要求 `game`。平台、官网、域名和手工关键词已知时应填写；GitHub repo 与 Cloudflare Pages project 不属于输入：

```json
{
  "schemaVersion": 3,
  "taskType": "site",
  "game": "Example Game",
  "platform": "roblox",
  "officialUrl": "https://www.roblox.com/games/123/example",
  "manualKeywords": ["Example Game codes", "Example Game best units"],
  "publish": true,
  "siteUrl": "https://example-game.wiki"
}
```

`manualKeywords` 最多 200 项，规范化和去重后作为 `user_provided` 来源进入 Guide Search；它们不会绕过风险过滤、证据门或 Basic Info profile。普通失败恢复不刷新，Worker 重试依赖已落盘 checkpoint。

一次提交 10 个游戏使用 `jobs/batch.example.json`：

```powershell
python gamewiki.py jobs submit-batch --config jobs\daily.json
```

整个 batch 先完整验证，任意一项字段错误时一个任务也不会入队；通过后每个游戏成为独立 job，互不阻塞。

后台队列只接受 `taskType: site`。广告任务、原始广告代码和广告环境变量不属于 Factory；交由独立广告 Agent 按 `docs/adsterra-environment-contract.md` 处理。

## 常用命令

```powershell
# 提交
python gamewiki.py jobs submit --config jobs\game.json

# 批量提交目录内 JSON
python gamewiki.py jobs submit-batch --config-dir jobs\batch

# 单个批量文件
python gamewiki.py jobs submit-batch --config jobs\daily.json

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
5. 每个站点创建新的 Private repo 和连接其 `main` 的 Git-integrated Pages 项目，自动设置 `NEXT_PUBLIC_SITE_URL` 并触发首次部署；后续 `main` push 由 Cloudflare 自动构建。
6. 未提供广告变量时零广告渲染；发布器不修改 Cloudflare Pages 环境变量。
7. 后台 schema 只包含站点生产字段；不得重新引入广告任务或旧 Vercel 广告自动化。
8. 站点 Job 成功时必须有 Private GitHub，且 `hosting.status` 为 `complete` 或 `awaiting_domain_configuration`。后者由运营者绑定自定义域名/DNS后另行执行 `verify:deploy`；验证日志固定保存为项目 `.gamewiki/deploy-verification.log`。
