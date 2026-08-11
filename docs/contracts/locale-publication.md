# 语言发布契约

Factory 新站默认只生成并发布 `en`：

`en`

核心 Worker 不再自动生成西班牙语，也不再创建第三个自然日的 `localeRelease` 子任务。`publication-plan.json` 仍是公开语言的唯一声明源；默认计划为 `generatedLocales=["en"]`、`publishedLocales=["en"]`、`releasePolicy.mode="english-only"`。

约束：

- `generatedLocales` 默认固定为 `en`。
- `publishedLocales` 只能是 `generatedLocales` 的连续前缀。
- 未公开语言不得出现在路由、sitemap 或 hreflang。
- 新语言上线前必须重新运行完整站点验证。
- 模板仍保留 `es/de/fr/ja` 能力，但 Factory 默认不生成。后续语言必须由 Growth Agent 根据真实查询语言、国家和排名页面提出方案，经用户批准后扩展现有 Private repo；不得重建整个站点。
- 显式扩展项目可以把 `generatedLocales` 改为例如 `["en","es"]`，并使用 `releasePolicy.mode="sequential"`、`intervalDays=3` 复用 locale 发布工具；这不是主流程默认行为。
