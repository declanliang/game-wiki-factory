# 运行与故障接手手册

## 正常运行

```powershell
cd C:\Users\liang\Documents\Games\game-wiki-factory
python gamewiki.py "GAME NAME"
```

默认网站目录是 `..\<game-slug>`。同一命令自动续跑。

并发执行：

```powershell
python gamewiki.py run-many "Game A" "Game B" --jobs 2 --llm-concurrency 6 --llm-per-key 2 --build-concurrency 1
```

`--jobs` 控制游戏进程数；其余参数分别限制全局 LLM、每个 key 和全局构建许可。默认 `2/6/2/1` 是本次双游戏实测后采用的稳健值；提高前先观察 429/5xx、内存和总耗时。状态、日志和续跑不需要寻找具体文件：

```powershell
python gamewiki.py status
python gamewiki.py logs <slug> --tail 150
python gamewiki.py resume <slug>
```

## 自动发布

GitHub Actions 设置 Secrets：`FACTORY_GITHUB_TOKEN`、`VERCEL_TOKEN` 以及生成/搜索/翻译 API key；设置 Variables：`FACTORY_GITHUB_OWNER`、可选 `VERCEL_TEAM_ID`。本地可以复用 `gh auth login` 与 `vercel login` 会话。发布器强制 GitHub 仓库为 Private，只创建/复用 Vercel 项目，不写任何 Vercel 环境变量。

```powershell
python gamewiki.py publish <slug>
```

需要无人值守生成后立即发布时，可用单游戏 `python gamewiki.py "GAME" --publish` 或多游戏 `python gamewiki.py run-many "A" "B" --jobs 2 --publish`。

已存在的 GitHub/Vercel 项目会复用。GitHub integration 未授权读取 Private repo 时，完成授权后重复同一命令。Actions 中运行 `Generate and publish game wikis`，`games_json` 输入合法 JSON 数组，例如 `["Game A", "Game B"]`。

Vercel 导入完成后，`.gamewiki/publish.json` 的 Vercel stage 会是 `awaiting_domain_configuration`。人工完成以下步骤后才算正式上线：绑定最终域名、设置生产 `NEXT_PUBLIC_SITE_URL`、触发生产部署、运行 `npm run verify:deploy`。不要把 Vercel 默认域名自动写入该变量。

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
- Guide Search 的 ToAPIs 请求遇到 SSL EOF、429 或常见 5xx/52x：自动指数退避重试，已完成的聚类 batch checkpoint 不会重做。
- 某语言缺失或截断：SEO Scout 只删除并重翻无效文件。
- 英文生成出现 `finish_reason=length`：客户端会以 10,000-token 上限和无表格紧凑提示词重试；仍失败会返回非零并把 Articles stage 标记为 failed。不要使用 overwrite。
- 翻译正文完整但 SERP 标题/描述略超限：流水线会本地压缩元数据后重新执行完整性校验，不重翻正文。
- LLM 返回余额不足：当前 key slot 会被禁用；所有 key 都无额度时立即停止剩余批次并保留已有文章。充值后不加 overwrite 续跑。
- 主题稀少：检查 Suggest 和多视频共同支持的机制主题；接受较少的可靠文章，不能合成 fallback 关键词。
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
- sitemap 的 loc/hreflang 目标全部直接 200（不接受 3xx）
- OG/Twitter image 正常
- hreflang 包含六语言和 x-default；每个 locale 页面 canonical 等于自身最终 URL
- 非英语分类描述、法律页和文章正文没有英语静默回退

本地 `example.com` 是未配置正式域名的预期状态。部署前设置 `NEXT_PUBLIC_SITE_URL` 后运行：

```powershell
npm run verify:deploy
```

`NEXT_PUBLIC_SITE_URL` 推荐填写完整 `https://...`；裸域名会自动补 HTTPS。它是公开站点 origin，不需要 Sensitive。`verify:deploy` 会读取线上 HTML 并检查 title、canonical、`og:url`、图片绝对 URL、sitemap/robots 和全部 loc/hreflang 直接 200，避免把跳转或 metadata 崩溃的 HTTP 200 当成成功。

## 工厂升级已有网站

修复通用模板或编排器后，从工厂再次执行同一游戏名。同步模板不会覆盖游戏的 `intake/`、`content/`、`.gamewiki/`、`node_modules/` 或本地环境文件，随后会重新物化并验证站点。
