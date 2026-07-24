# OpenClaw Game Wiki Operator 使用规范

这是用户、OpenClaw Agent 和后续 AI 之间的稳定接口。Agent 是控制面：验证输入、提交后台任务、查询状态和汇报异常；`gamewiki-worker` 才执行几十分钟的采集、生成、翻译、构建和发布。聊天断线或上下文清空不能终止任务。

## 用户应该提供什么

新站只要求游戏名；已知信息应尽量填写，避免身份歧义。不要填写 GitHub repo、Cloudflare Pages project 或任何密钥。所有未来游戏都按新项目处理，不接受 rebuild/旧 repo 覆盖输入。

```json
{
  "game": "GAME NAME",
  "platform": "roblox",
  "officialUrl": "https://www.roblox.com/games/PLACE_ID/SLUG",
  "siteUrl": "https://game-domain.example",
  "manualKeywords": ["GAME NAME codes", "GAME NAME best units"],
  "publish": true
}
```

- `platform`：`roblox`、`steam` 或 `auto`。
- Steam 的 `officialUrl` 必须是 Steam Store App URL。
- `siteUrl` 可省略；运营者手工连接 Cloudflare Pages 后再决定正式域名，并设置匹配的 `NEXT_PUBLIC_SITE_URL`。
- 单站的 `schemaVersion`、`taskType: site` 和默认 operation 由系统自动补齐，用户无需填写。
- `manualKeywords` 可选，最多 200 项。它们会作为 `user_provided` 来源进入 Guide Search，但仍受风险、证据和分类边界约束。
- 不填写 `operation`；失败续跑只重试原 Job。

推荐给 OpenClaw 的话：

```text
请按照附件 game.json 提交 Game Wiki 后台任务。先验证 JSON，再返回 job ID。
不要在聊天进程运行流水线，不要向我索要 repo/Cloudflare Pages 项目名称，不要打印密钥。
以后查询时以后台数据库和日志为准；只有线上验收完成后才能告诉我成功。
```

## 一次提交多个游戏

```json
{
  "schemaVersion": 1,
  "taskType": "siteBatch",
  "batchName": "daily-10",
  "defaults": {"platform": "roblox", "publish": true},
  "games": [
    {"game": "Game One", "officialUrl": "https://www.roblox.com/games/1/x", "siteUrl": "https://one.example"},
    {"game": "Game Two", "officialUrl": "https://www.roblox.com/games/2/y"}
  ]
}
```

Prompt：

```text
请验证并提交附件 daily.json。整个 batch 任一配置无效时不要提交任何任务；
通过后返回每个游戏对应的 job ID。后台自行按并发限制处理，不要开多个聊天前台进程。
```

## 后续添加广告

OpenClaw 不接收 Cloudflare Pages 广告任务，也不要让用户把原始代码粘贴进聊天正文。

```text
Factory 默认的 Cloudflare Pages 流程不要提交 `taskType: ads` 后台任务。广告需要在目标游戏仓库用 `npm run ads:import` 校验，
再由运营者把 `AD_*_B64` 手工写入 Pages Production Secret 并重新部署；不得打印或提交 code 字段。
```

手工广告配置不重跑内容。缺少广告变量时站点不展示广告、不保留空白；配置后必须验证七个 `/api/ads/<format>` 路由的代码哈希。

## 生产版本认定

当前稳定版本读取根目录 `release.json`。普通 Git commit 不改变产品版本。OpenClaw 不得按日期、外观或文章数量推断版本；必须检查任务结果中的 `factoryRelease` 和站点的 `intake/factory-release.json`。线上认证还必须由运营者完成 Cloudflare Pages 验收并登记到 release 站点清单。

## 查询、异常和完成汇报

用户查询：

```text
请实时查询我这批 Game Wiki 任务，按游戏返回 job ID、状态、当前阶段、尝试次数和最后错误。
不要根据之前聊天记忆回答。
```

Agent 每次必须先执行 `jobs list --json`，再对目标执行 `jobs status JOB_ID --json`。成功任务的 `result` 是清理 workspace 后仍保留的非敏感摘要，包含文章数、分类、Private GitHub 和 Cloudflare Pages 手动操作提示；不要绕过 CLI 直接读取 secrets。只有下列条件全部满足才能报告生成完成：

1. job 为 `succeeded`，manifest 必需阶段完成；
2. GitHub repo 为 Private；
3. `publish.json` 中 `stages.hosting.provider=cloudflare-pages` 且 `status=manual_action_required`，或运营者已另行完成线上部署和验收；
4. Factory 默认流程不存在后台广告任务；广告由运营者另行部署和验收。

完成汇报固定包含：游戏、job ID、英文/全部语言文章数、分类数、内容机会报告路径、Private repo、Cloudflare Pages 手工连接提示和广告状态。未手动部署前不得声称网站已线上验证。

`needs_attention` 固定汇报：第一个失败阶段、根因、日志路径、是否需要用户动作、是否会重复 API 成本。网络/429/5xx 由 Worker 有界重试；不要创建第二个同游戏任务。用户修复密钥、余额、DNS 或权限后，重试原 job，复用 checkpoint。

## 状态变化通知

任务终态会进入持久化 notification outbox。通知轮询只能读取非敏感摘要：

```bash
/usr/local/bin/gamewiki jobs notifications --json
/usr/local/bin/gamewiki jobs notifications --ack 12 13
```

OpenClaw cron 建议每2分钟执行一次 `/usr/local/bin/gamewiki notifier --once`。这是确定性 dispatcher，不调用 LLM；它将 `succeeded`、`failed`、`cancelled` 或 `needs_attention` 送到配置渠道，只有发送命令成功后才确认 notification ID。对话断线、Agent 重启和重复轮询都不会丢消息；未确认消息会退避重试。每日汇总可以另设 Agent cron，但不能代替终态通知。

服务器还运行每分钟一次的确定性 Supervisor。文章生成或翻译已保存部分 checkpoint、但 ToAPIs/网络在有界 Worker 重试后仍失败时，Supervisor 会自动恢复同一 Job；OpenClaw 不需要询问用户，也不得创建替代 Job。身份、凭据、余额、schema、代码、构建和发布安全问题不会被 Supervisor 接管，仍按 `needs_attention` 汇报。

批量生产时，用户只需发送一个 `siteBatch` JSON 并要求提交后台队列：

```json
{
  "schemaVersion": 3,
  "taskType": "siteBatch",
  "batchName": "daily-roblox",
  "defaults": {
    "operation": "new",
    "platform": "roblox",
    "publish": true
  },
  "games": [
    {
      "game": "Game One",
      "officialUrl": "https://www.roblox.com/games/123/Game-One",
      "siteUrl": "https://game-one.wiki"
    },
    {
      "game": "Game Two",
      "officialUrl": "https://www.roblox.com/games/456/Game-Two"
    }
  ]
}
```

标准 Prompt：

```text
请验证并使用 jobs submit-batch 提交附件中的 Game Wiki 批量 JSON。返回每个 Job ID 后结束本轮，不要在对话进程运行流水线。后台 Worker、Supervisor 和 Notifier 会负责执行、checkpoint-safe 恢复和终态通知。只有收到最终 needs_attention 时才汇报根因并升级，不要创建重复 Job。
```

在尚未绑定具体聊天渠道前，只部署 outbox，不得假装已经具备主动送达能力。渠道绑定完成后，应做一次“生成测试事件 → 收到消息 → acknowledge → 再次查询为空”的端到端验收。

## 故障处理权限

- **Worker 自动处理**：429、常见 5xx、SSL/网络超时等已分类的瞬时错误；使用有界重试和 checkpoint。
- **Agent 可以处理**：查询、读日志、按现有 runbook 重试/取消，以及权威官网 URL 明确消除歧义后的输入修正。Agent 不得扩大 API 重试次数。
- **必须升级给 Codex/基础设施维护者**：任何源代码、测试、数据库、任务状态机、Basic Info、关键词、内容/QA、GitHub/Cloudflare 发布、广告匹配或成本控制逻辑问题。

Agent 发现疑似代码 bug 时只能报告证据并保持任务为 `needs_attention`。禁止直接修改服务器工作树、提交 Git、拉取代码或重启服务。正式修复必须在 Factory 本地完成回归测试、提交 GitHub，再在无运行任务的维护窗口部署。

## Agent 的安全边界与经验

- 每次从数据库、manifest、receipt 和日志重新建立事实，不依赖聊天上下文。
- 不读取、显示或复制 `factory.env`；不把真实任务 JSON、广告代码、日志或 `.gamewiki` 提交 Git。
- GitHub 只能是 Private；拒绝 Public 请求。
- 不因文章数量少就造 fallback。先读 `content-opportunity-report.json`：公开资料少可以接受；明显跨游戏内容必须删除。
- Cloudflare Pages 显示部署成功、Git push 成功或本地 build 成功都不是最终成功；线上自动验证是发布事务的最后一步。
- 同名目标目录或 repo 已存在时停止并升级，不得自动删除、覆盖或把它解释为旧站升级。
- 广告标题是严格协议：`Native Banner`、`Banner 468x60`、`Banner 300x250`、`Banner 160x300`、`Banner 160x600`、`Banner 320x50`、`Banner 728x90`，不可凭 alias 猜测位置。
