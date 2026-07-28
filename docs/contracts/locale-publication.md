# 多语言分批发布契约

文章和站点文案一次生成 `en/es/de/fr/ja`，但公开路由按以下顺序逐步增加：

`en → es → de → fr → ja`

每 3 个自然日于 Asia/Shanghai 10:00 发布下一个语言。SQLite 子任务 `localeRelease` 修改 `intake/publication-plan.json`，提交 Private GitHub `main`，再由 Git-integrated Cloudflare Pages 自动构建。

约束：

- `generatedLocales` 始终是五种固定语言。
- `publishedLocales` 只能是上述顺序的连续前缀。
- 未公开语言不得出现在路由、sitemap 或 hreflang。
- 每一波发布都复用已生成译文，不重新调用付费翻译。
- 新语言上线前必须重新运行完整站点验证。
