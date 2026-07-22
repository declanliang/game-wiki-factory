# 运行与故障接手手册

## 正常运行

```powershell
cd C:\Users\liang\Documents\Games\game-wiki-factory
Copy-Item jobs\example.json jobs\my-game.json
# 编辑 my-game.json 后执行：
python gamewiki.py --config jobs\my-game.json
```

配置文件必须明确 `game`、`platform` 和已知的 `officialUrl`；Steam 使用 Store App URL，Roblox 使用 Experience URL。`publish: true` 会完成 Private GitHub 和 Vercel production 发布。真实 `jobs/*.json`、配置快照和日志都被 Git 忽略。

直接参数模式仍可用于调试：

```powershell
python gamewiki.py "Funnel Runners" --platform steam --official-url "https://store.steampowered.com/app/3712080/Funnel_Runners/"
python gamewiki.py "Hellhole" --platform roblox
```

`auto` 模式会依次尝试 Roblox 和 Steam。平台身份不确定属于阻断错误，应补充官方 URL 或显式平台，不要调低身份阈值。

默认网站目录是 `..\<game-slug>`。同一配置自动续跑；完整配置快照和终端日志位于项目 `.gamewiki/configs/` 与 `.gamewiki/logs/`。

并发执行：

```powershell
python gamewiki.py run-many "Game A" "Game B" --jobs 2 --llm-concurrency 6 --llm-per-key 2 --build-concurrency 1
```

同名或易混淆游戏应使用 `--games-file` 的 TSV 格式：`游戏名<TAB>roblox|steam<TAB>官方 URL`。这样每个并发子进程都使用独立官方身份，仍由同一监督器限流。

`--jobs` 控制游戏进程数；其余参数分别限制全局 LLM、每个 key 和全局构建许可。默认 `2/6/2/1` 是本次双游戏实测后采用的稳健值；提高前先观察 429/5xx、内存和总耗时。状态、日志和续跑不需要寻找具体文件：

单个 SEO Scout 生成进程默认最多并发 3 个长文章请求；两游戏并发时总量仍可达到 6。不要把单进程并发直接提高到 6：真实长文生成出现过连续 `Server disconnected`，重试开销反而更高。

```powershell
python gamewiki.py status
python gamewiki.py logs <slug> --tail 150
python gamewiki.py resume <slug>
```

## 自动发布

GitHub Actions 设置 Secrets：`FACTORY_GITHUB_TOKEN`、`VERCEL_TOKEN` 以及生成/搜索/翻译 API key；设置 Variables：`FACTORY_GITHUB_OWNER`、可选 `VERCEL_TEAM_ID`。本地发布会优先读取 factory `.env`，没有 token 时复用 `gh auth login` 与 `vercel login` 会话。发布器强制 GitHub 仓库为 Private；只有明确传入 `--site-url` 才会写 Production 的公开 canonical 环境变量，并在环境配置完成后触发 production deployment。

```powershell
python gamewiki.py publish <slug>
```

需要无人值守生成后立即发布时，可用单游戏 `python gamewiki.py "GAME" --publish` 或多游戏 `python gamewiki.py run-many "A" "B" --jobs 2 --publish`。

已存在的 GitHub/Vercel 项目会复用。GitHub integration 未授权读取 Private repo 时，完成授权后重复同一命令。Actions 中运行 `Generate and publish game wikis`，`games_json` 输入合法 JSON 数组，例如 `["Game A", "Game B"]`。

Vercel 导入完成后，未传 `--site-url` 时 `.gamewiki/publish.json` 的 Vercel stage 会是 `awaiting_domain_configuration`，但模板会使用 Vercel 自动 production URL，绝不输出 `example.com`。已知正式域名时传 `--site-url`，发布器会配置 Production；随后绑定域名、触发生产部署并运行 `npm run verify:deploy`。

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
- V4 联网背景研究会生成 `llm/game-context.json.page_opportunities`；检查 `llm/rejected.json.opportunity_rejected` 可区分“没有发现”和“发现但证据/分类门槛不足”。该契约版本变化会使旧 context checkpoint 自动失效，但不会重做 Suggest/DataForSEO 原始采集。
- Guide Search 的 ToAPIs 请求遇到 SSL EOF、429 或常见 5xx/52x：自动指数退避重试，已完成的聚类 batch checkpoint 不会重做。
- 某语言缺失或截断：SEO Scout 只删除并重翻无效文件。
- 英文生成出现 `finish_reason=length`：客户端会以 10,000-token 上限和无表格紧凑提示词重试；仍失败会返回非零并把 Articles stage 标记为 failed。不要使用 overwrite。
- 翻译正文完整但 SERP 标题/描述略超限：流水线会本地压缩元数据后重新执行完整性校验，不重翻正文。
- 多个不同页面被翻译成同一个泛化标题：翻译收尾会根据英文 source slug 追加短主题限定词，本地消歧，不重翻正文。
- LLM 返回余额不足：当前 key slot 会被禁用；所有 key 都无额度时立即停止剩余批次并保留已有文章。充值后不加 overwrite 续跑。
- 主题稀少：同时检查 Suggest、多视频共同支持的机制主题、`page_opportunities` 及拒绝原因。简单游戏接受较少页面；资料丰富的游戏应保留不同玩家意图和具体实体页，不能为旧的 3–5 篇经验值过度合并，也不能合成 fallback 主题。
- Codes/Tier List/实体页异常：确认 Basic Info profile 是否允许对应分类。Tier List 还必须有可比较实体证据；Codes 不得编造兑换码；Calculator/Planner 等工具页不属于当前流水线。
- Steam Deck：`full controller support` 不等于 Deck Verified/Playable；没有官方兼容性等级时只能写“未确认”和谨慎测试建议。
- 模板失败：修工厂 `template/` 后重跑，不能重新付费生成上游内容。

## 有成本的参数

- `--refresh-basic`
- `--recluster-keywords`
- `--overwrite-articles`

使用前必须在日志或交付说明中记录原因。

## 翻译完整性

翻译任务使用独立 reasoning 配置。客户端拒绝非 `finish_reason=stop` 的响应；落盘前对照英文检查标题层级、列表、表格、FAQ、Callout、长度和结尾。不要手工补标签掩盖截断正文。

`--recluster-keywords` 可能改变最终 8 个 published 分类。SEO Scout 中未入选的新旧文章都会保留为 checkpoint；编排器重建 `intake/articles` 时只复制当前 site-plan 分类。因此看到 content-pipeline 中存在旧分类是正常的，部署输入和网站中不应出现它们。

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
- 首页 Hero 使用真实游戏图；有至少两篇文章的高价值分类会生成本地化专题入口，且所有专题链接存在

本地 `example.com` 是未配置正式域名的预期状态。部署前设置 `NEXT_PUBLIC_SITE_URL` 后运行：

```powershell
npm run verify:deploy
```

`NEXT_PUBLIC_SITE_URL` 推荐填写完整 `https://...`；裸域名会自动补 HTTPS。它是公开站点 origin，不需要 Sensitive。`verify:deploy` 会读取线上 HTML 并检查 title、canonical、`og:url`、图片绝对 URL、sitemap/robots 和全部 loc/hreflang 直接 200，避免把跳转或 metadata 崩溃的 HTTP 200 当成成功。

## 已有网站的两类操作

仅修复通用模板或编排器时，从 Factory 再次执行同一游戏名。同步模板不会覆盖游戏的 `intake/`、`content/`、`.gamewiki/`、`node_modules/` 或本地环境文件；不使用 refresh，即可复用内容 checkpoint、重新物化并验证站点。

旧站尚未使用当前信息扩充流程时，不走模板升级捷径，提交 `operation: rebuild`。系统把它视为新站完整采集和生成，旧 workspace 先归档，旧 Private repo 在创建备份 tag 后整树替换，原 Vercel project、域名和广告等环境变量继续复用。

## Adsterra 配置

每个网站单独申请 Adsterra app/ad units。广告配置全部可选：缺少某一格式时，该格式及其外层间距均不渲染。Factory 日常操作应提交 `taskType: ads` 的原始平台 JSON；系统严格校验游戏/域名、7 个逐字标题、尺寸和脚本 key，自动转换并写入对应 Vercel Production 变量，不需要人工 Base64。单站本地调试仍可使用 `ad.txt` + `npm run ads:import`。环境变量更新后必须重新部署。
