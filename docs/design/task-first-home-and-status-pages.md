# Task-first 首页与状态页规范

本规范是 `v1_0722` 的兼容增强，不创建 `/wiki/` 分类，也不改变“一篇文章解决一个主要玩家意图”的原则。

## 信息架构

- 网站本身就是 Wiki，因此不创建 `/wiki/` 路由或名为 Wiki 的内容分类。
- `/guide/` 保留为真实 Guide 分类的聚合页；文章仍使用 `/<category>/<article-slug>`。
- Codes、Tier List、Updates、Progression、Mechanics 等只有在 site-plan 发布时才进入导航。
- 首页最先展示由真实文章生成的任务入口，帮助玩家按“开始、提升、解决当前问题”等意图进入内容，而不是制造工具页。

## 首页

- Hero 保持核心名称、说明、CTA 和关键统计，并控制首屏高度。
- Hero 下方显示紧凑的官方身份条：Roblox Place ID/Steam App ID、开发者、平台，并链接官方页面。
- Featured 内容提前到 About 之前，作为任务路由；最多展示六个真实文章入口。
- About、Guide Sections、分类、更新、FAQ 和广告布局继续保留。

## 状态型页面

允许 Codes、Update 或官方入口相关的“当前无结果/未验证”页面，但必须同时满足：

1. 存在明确的本游戏搜索意图；
2. 调研证实当前不可用、无有效结果或尚未验证；
3. 页面直接回答当前状态，写明检查范围/时间、排错或安全下一步，以及什么证据会改变答案；
4. 不得用空泛状态页凑数量，不得编造 code、版本、排名、日期或官方社区链接。

Tier List 仍要求游戏确实存在可排名实体；没有可排名集合时不创建虚假 Tier List。

## 验收

- 首页任务入口只能指向已生成文章；不得产生 404。
- 身份条必须由官方 URL 和 Basic Info 字段机械生成。
- 六语言文章树、导航、sitemap 与 site-plan 保持一致。
- production 发布必须通过现有线上 canonical、robots、sitemap 和全部 loc/hreflang URL 验收。
