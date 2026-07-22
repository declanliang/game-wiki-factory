# OpenClaw Game Wiki Operator 使用规范

这是用户、OpenClaw Agent 和后续 AI 之间的稳定接口。Agent 是控制面：验证输入、提交后台任务、查询状态和汇报异常；`gamewiki-worker` 才执行几十分钟的采集、生成、翻译、构建和发布。聊天断线或上下文清空不能终止任务。

## 用户应该提供什么

新站/续跑只要求游戏名；已知信息应尽量填写，避免身份歧义。不要填写 GitHub repo、Vercel project 或任何密钥：新站由系统创建，旧站由 receipt/slug 自动复用。

```json
{
  "game": "GAME NAME",
  "platform": "roblox",
  "officialUrl": "https://www.roblox.com/games/PLACE_ID/SLUG",
  "siteUrl": "https://game-domain.example",
  "publish": true
}
```

- `platform`：`roblox`、`steam` 或 `auto`。
- Steam 的 `officialUrl` 必须是 Steam Store App URL。
- `siteUrl` 可省略；省略时使用并验证 Vercel 默认 production 域名。
- 单站的 `schemaVersion`、`taskType: site` 和默认 operation 由系统自动补齐，用户无需填写。
- 新站不填写 `operation`；失败续跑仍提交/重试原 job。
- 旧半成品彻底重做时，在与 `game` 同级的顶层填写 `"operation": "rebuild"`。它会完整重新付费采集/生成，创建 repo 备份 tag 后替换原站：

```json
{
  "operation": "rebuild",
  "game": "OLD GAME NAME",
  "platform": "roblox",
  "officialUrl": "https://www.roblox.com/games/PLACE_ID/SLUG",
  "siteUrl": "https://existing-domain.example",
  "publish": true
}
```

推荐给 OpenClaw 的话：

```text
请按照附件 game.json 提交 Game Wiki 后台任务。先验证 JSON，再返回 job ID。
不要在聊天进程运行流水线，不要向我索要 repo/Vercel 名称，不要打印密钥。
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

直接提交 Adsterra 导出的原始 JSON，并增加 `taskType: "ads"` 和建议填写的 `game`。不要手工 Base64，不要把原始代码粘贴进聊天正文。

```text
请把附件 ads.json 作为独立广告任务提交。不得打印 code 字段。
必须先完成游戏、domain_name、Vercel project、七个 title、尺寸和脚本 key 的严格匹配；
验证全部通过后才允许写环境变量和重新部署。返回 job ID。
```

广告任务不重跑内容。缺少广告变量时站点不展示广告、不保留空白；配置后必须验证七个 `/api/ads/<format>` 路由的代码哈希。

## 生产版本认定

当前稳定版本读取根目录 `release.json`。普通 Git commit 不改变产品版本。OpenClaw 不得按日期、外观或文章数量推断版本；必须检查任务结果中的 `factoryRelease`、站点的 `intake/factory-release.json`，并以 `docs/releases/v1_0722-sites.json` 为最终登记依据。旧站普通续跑不会获得版本标记，必须提交顶层 `operation: rebuild`。

## 查询、异常和完成汇报

用户查询：

```text
请实时查询我这批 Game Wiki 任务，按游戏返回 job ID、状态、当前阶段、尝试次数和最后错误。
不要根据之前聊天记忆回答。
```

Agent 每次必须先执行 `jobs list --json`，再对目标执行 `jobs status JOB_ID --json`。成功任务的 `result` 是清理 workspace 后仍保留的非敏感验收摘要，包含文章数、分类、Private GitHub、Vercel 和线上验证；不要绕过 CLI 直接读取 secrets。只有下列条件全部满足才能报告成功：

1. job 为 `succeeded`，manifest 必需阶段完成；
2. GitHub repo 为 Private；
3. Vercel production deployment 完成；
4. `publish.json` 中 `stages.onlineVerification.status=complete`；
5. 线上首页 metadata/canonical、sitemap、robots 和所有 loc/hreflang 目标直接返回 200；
6. sitemap/robots/canonical 不含 `example.com`；
7. 若是广告任务，七个广告路由均为本次代码哈希。

完成汇报固定包含：游戏、job ID、英文/全部语言文章数、分类数、内容机会报告路径、Private repo、production URL、线上验证状态/日志、广告状态。Vercel 显示 READY 但线上门未通过时，只能报告“部署完成、验收失败/进行中”。

`needs_attention` 固定汇报：第一个失败阶段、根因、日志路径、是否需要用户动作、是否会重复 API 成本。网络/429/5xx 由 Worker 有界重试；不要创建第二个同游戏任务。用户修复密钥、余额、DNS 或权限后，重试原 job，复用 checkpoint。

## 状态变化通知

任务终态会进入持久化 notification outbox。通知轮询只能读取非敏感摘要：

```bash
/usr/local/bin/gamewiki jobs notifications --json
/usr/local/bin/gamewiki jobs notifications --ack 12 13
```

OpenClaw 的通知 cron 建议每 2–5 分钟运行一次。它必须先读取待通知项，将 `succeeded`、`failed`、`cancelled` 或 `needs_attention` 消息送达绑定渠道，然后只确认已经成功送达的 notification ID。对话断线、Agent 重启和重复轮询都不会丢消息；未确认消息会保留。每日汇总可以另设 cron，但不能代替终态通知。

在尚未绑定具体聊天渠道前，只部署 outbox，不得假装已经具备主动送达能力。渠道绑定完成后，应做一次“生成测试事件 → 收到消息 → acknowledge → 再次查询为空”的端到端验收。

## 故障处理权限

- **Worker 自动处理**：429、常见 5xx、SSL/网络超时等已分类的瞬时错误；使用有界重试和 checkpoint。
- **Agent 可以处理**：查询、读日志、按现有 runbook 重试/取消，以及权威官网 URL 明确消除歧义后的输入修正。Agent 不得扩大 API 重试次数。
- **必须升级给 Codex/基础设施维护者**：任何源代码、测试、数据库、任务状态机、Basic Info、关键词、内容/QA、GitHub/Vercel 发布、广告匹配或成本控制逻辑问题。

Agent 发现疑似代码 bug 时只能报告证据并保持任务为 `needs_attention`。禁止直接修改服务器工作树、提交 Git、拉取代码或重启服务。正式修复必须在 Factory 本地完成回归测试、提交 GitHub，再在无运行任务的维护窗口部署。

## Agent 的安全边界与经验

- 每次从数据库、manifest、receipt 和日志重新建立事实，不依赖聊天上下文。
- 不读取、显示或复制 `factory.env`；不把真实任务 JSON、广告代码、日志或 `.gamewiki` 提交 Git。
- GitHub 只能是 Private；拒绝 Public 请求。
- 不因文章数量少就造 fallback。先读 `content-opportunity-report.json`：公开资料少可以接受；明显跨游戏内容必须删除。
- Vercel READY、Git push 成功或本地 build 成功都不是最终成功；线上自动验证是发布事务的最后一步。
- 旧站重建不解决旧代码冲突，直接使用当前流程重做并替换 repo；失败时保留旧线上版本和备份 tag。
- 广告标题是严格协议：`Native Banner`、`Banner 468x60`、`Banner 300x250`、`Banner 160x300`、`Banner 160x600`、`Banner 320x50`、`Banner 728x90`，不可凭 alias 猜测位置。
