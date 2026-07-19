# 运行与故障接手手册

## 正常运行

```powershell
cd C:\Users\liang\Documents\Games\game-wiki-factory
python gamewiki.py "GAME NAME"
```

默认网站目录是 `..\<game-slug>`。同一命令自动续跑。

## 排查顺序

假设目标是 `C:\Users\liang\Documents\Games\hellhole`：

1. `.gamewiki/manifest.json` 的 `status/error/stages/currentAttempt`。
2. `.gamewiki/logs/orchestrator-*.log` 的完整命令、cwd、输出和 traceback。
3. 对应的 Basic Info、Guide Search、SEO Scout 或 site stage 日志。
4. `.gamewiki/planning/site-plan.json` 的 rejected/unfulfilled/published。
5. `.gamewiki/content-pipeline/out/qa_results.json` 与 `qa_removed.jsonl`。
6. `intake/` 与生成的 `content/` 是否一致。

## 恢复原则

- 默认直接重跑同一命令；所有阶段先验证 checkpoint。
- API 限速、网络错误：直接重跑，不加 overwrite。
- Guide Search 聚类失败：复用 `.gamewiki/planning/guide-search/raw`。
- 某语言缺失或截断：SEO Scout 只删除并重翻无效文件。
- QA 后少于 4 个分类：补充真实同游戏需求，不能降低相关性门槛。
- 模板失败：修工厂 `template/` 后重跑，不能重新付费生成上游内容。

## 有成本的参数

- `--refresh-basic`
- `--recluster-keywords`
- `--overwrite-articles`

使用前必须在日志或交付说明中记录原因。

## 翻译完整性

翻译任务使用独立 reasoning 配置。客户端拒绝非 `finish_reason=stop` 的响应；落盘前对照英文检查标题层级、列表、表格、FAQ、Callout、长度和结尾。不要手工补标签掩盖截断正文。

## 网站验收

```powershell
cd C:\Users\liang\Documents\Games\<game-slug>
npm run launch:site
```

成功必须同时满足：

- intake 0 error
- 六语言文章树一致
- 全部 MDX 结构通过
- TypeScript 通过
- 配置同步通过
- production build 通过
- sitemap 全 URL 200
- OG/Twitter image 正常
- hreflang 包含六语言和 x-default

本地 `example.com` 是未配置正式域名的预期状态。部署前设置 `NEXT_PUBLIC_SITE_URL` 后运行：

```powershell
npm run verify:deploy
```

## 工厂升级已有网站

修复通用模板或编排器后，从工厂再次执行同一游戏名。同步模板不会覆盖游戏的 `intake/`、`content/`、`.gamewiki/`、`node_modules/` 或本地环境文件，随后会重新物化并验证站点。
