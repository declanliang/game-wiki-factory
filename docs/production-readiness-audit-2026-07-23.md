# 生产就绪审计（2026-07-23）

## 结论

Factory 的主要安全边界已经代码化：游戏 repo 强制 Private、密钥文件发布前扫描、Vercel token 不进入 argv、官方身份歧义阻断、付费阶段 checkpoint 复用、线上 SEO 验收是成功条件。后台 Worker、Supervisor、Notifier 将长任务与 OpenClaw 对话解耦。

本次高优先级修复是 API 额度耗尽：错误被独立标记为 `quota_exhausted`，立即生成明确通知，停止自动推进，并禁止 Supervisor 因已有文章/翻译 checkpoint 而误恢复。

线上抽查曾发现 `anime-expeditions-game.wiki` 的 HTML 与 sitemap 语言不完整。验证器此前只验证“已有目标可访问”，没有验证固定语言集合。本次已把产品固定语言加 `x-default` 完整性加入本地和线上硬门。2026-07-23 产品策略进一步缩减为 `en/es/de/fr/ja`，不再生成韩语；旧站可用确定性迁移工具删除退休 locale，无需重做内容。该站历史 Vercel project 名为 `anime-expeditions2`，不能按 GitHub repo 名推断。

## 已检查范围

- 控制面：任务状态、SQLite lease、重试与通知、清理路径、OpenClaw 权限。
- 发布：GitHub Private 后置验证、远端替换备份、Vercel token/env、广告代码隔离。
- Pipeline：Roblox/Steam 身份边界、证据门、checkpoint、翻译完整性。
- 模板与 SEO：robots、sitemap、canonical、hreflang、JSON-LD、404、metadata、内链、多语言、广告/媒体性能风险。
- 恢复：只凭 GitHub 在 Windows 和 Ubuntu 重建，systemd、OpenClaw、备份与回滚。

## 仍需运营持续关注

- AI 生成事实允许小范围误差，但错误官方链接、跨游戏实体和虚构代码仍是高信任风险；上线后应抽查流量最高页面。
- 五语言规模化翻译可能产生自然度和重复标题问题；确定性结构校验不能代替母语质量抽检。
- Adsterra 与 YouTube 会增加第三方脚本、隐私和 Core Web Vitals 风险。广告 iframe 已隔离并预留尺寸，但真实 CLS/INP 需在有流量和广告填充后用 Search Console/CrUX 观察。
- 模板已加入 HSTS、`nosniff`、SAMEORIGIN、严格 referrer 和 Permissions Policy。暂未启用 CSP：Adsterra 的动态第三方脚本域名需要先建立并持续维护允许清单，否则严格 CSP 会阻断收入代码。
- 法律页是模板内容，不等同于特定司法辖区法律意见；启用广告/分析后应复核隐私、Cookie 和未成年人相关要求。
- SQLite 适合当前单机两路 Worker；不要把同一数据库放到网络文件系统或多主机并发写。横向扩展前迁移到服务器数据库和对象存储。
- `.gamewiki` 不进 Git。已发布站点可恢复，未发布任务的原始 checkpoint 在服务器全损时会丢失。
- Search Console、Bing Webmaster、真实流量、索引覆盖和 Core Web Vitals 不在代码仓库内，需按站点持续监控。

## 发布门槛

每个站点必须满足：Private repo、生产 build、五语言内容一致、self-canonical、reciprocal hreflang 与 x-default、sitemap/robots 同源、全部 sitemap loc/hreflang 直接 200、线上 metadata/OG 验证通过。未配置广告变量必须零渲染、零占位。
