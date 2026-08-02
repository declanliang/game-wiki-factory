# 多语言分批发布契约

Factory 新站一次只生成 `en/es`，公开路由按以下顺序增加：

`en → es`

英语在建站当天公开，西班牙语在第三个自然日于 Asia/Shanghai 10:00 发布。SQLite 子任务 `localeRelease` 修改 `intake/publication-plan.json`，提交 Private GitHub `main`，再临时 clone 该 commit 并通过 `wrangler deploy` 重新发布同一个 Workers Static Assets 站点。该计划持久化在服务器数据库中，不依赖原始建站 Job 的租约或临时 workspace。

约束：

- `generatedLocales` 默认固定为 `en/es`。
- `publishedLocales` 只能是上述顺序的连续前缀。
- 未公开语言不得出现在路由、sitemap 或 hreflang。
- 西班牙语发布复用建站时已生成的译文，不重新调用付费翻译。
- 新语言上线前必须重新运行完整站点验证。
- 模板仍保留 `de/fr/ja` 能力，但 Factory 默认不生成。后续语言必须由 Growth Agent 根据真实查询语言、国家和排名页面提出方案，经用户批准后扩展现有 Private repo；不得重建整个站点。
