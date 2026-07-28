# 新站输入契约

Factory 只接受 Roblox 或 Steam 的全新站点任务。每个任务至少提供：

- `game`：面向用户的游戏名。
- `platform`：`roblox` 或 `steam`。
- `officialUrl`：Roblox game URL 或 Steam app URL；平台 ID 以该 URL 为准。
- `publish`：是否完成 Private GitHub 与 Cloudflare Pages 发布。

可选输入：

- `siteUrl`：正式域名。提供后，Pages Production 的 `NEXT_PUBLIC_SITE_URL` 自动写为该 origin；域名绑定和 DNS 仍由运营者完成。
- `manualKeywords`：人工收集的关键词。它们只增加发现入口，仍要通过风险过滤、证据门、Basic Info profile 和最终编辑门。

固定约束：

- 每个游戏都从新的 `../<slug>/` 目录开始，不接受 rebuild、fullBuild 或覆盖旧仓库。
- 生成语言固定为 `en/es/de/fr/ja`，公开语言由 `publication-plan.json` 控制。
- `site-plan.json` 是语言与分类唯一事实源；最多发布 8 类。
- 调研/cache/日志写入游戏根 `.gamewiki/`，最终模板输入写入游戏根 `intake/`。
- Factory 根 `.env` 是唯一密钥配置；禁止复制、打印或提交。

示例见 `jobs/example.json` 与 `jobs/batch.example.json`。
