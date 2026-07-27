# Game Wiki Factory 架构

## 仓库边界

`game-wiki-factory` 是控制面和全部通用源码的唯一 Git 仓库。具体游戏是独立的数据面和部署仓库：

```text
Games/
├─ game-wiki-factory/       通用代码、模板、契约、测试、文档
├─ hellhole/                独立 Next.js/GitHub/Cloudflare Pages 项目
└─ another-game/            独立 Next.js/GitHub/Cloudflare Pages 项目
```

工厂不保存真实游戏 output。游戏仓库不保存 API key，也不在 Cloudflare Pages 调用搜索或 LLM。

## 控制面

`gamewiki.py` 是人类入口，调用 `orchestrate_wiki.py`。编排器负责：

1. 创建或识别 `Games/<slug>`。
2. 把付费/可恢复状态固定在 `<slug>/.gamewiki/`。
3. 验证 checkpoint 后才允许跳过 stage。
4. 生成 `<slug>/intake/` 最终输入。
5. 把 `template/` 同步到游戏根，不覆盖 intake、content、node_modules 或 `.gamewiki`。
6. 机械物化内容并执行生产验收。

`gamewiki.py run-many` 是多项目监督器。每个游戏仍以独立进程运行；监督器提供共享许可服务，原子限制 `llm`、`llm-key-N` 和 `build` 资源，并为每个进程分配独立验证端口。并发因此不会把单 key 压力或本机 build 峰值按游戏数放大。

## 数据流

```text
游戏名 + 可选 platform / official URL
  → pipeline/basic-info
      平台解析器 → Roblox adapter 或 Steam adapter
      官方身份、规范事实、首页、hero/favicon、固定五语言、category candidates
  → pipeline/guide-search
      Google Suggest 主词+a–z、DataForSEO、去重视频标题证据、联网系统/实体机会、语义聚类与淘汰审计
      → content-opportunity-report（来源量、候选漏斗、实体覆盖、拒绝原因）
  → planner / project_contract.py
      game-profile + keywords → site-plan
  → pipeline/seo-scout
      search → collect → generate → topic QA → translate
  → intake
      identity + site content + site plan + assets + 5-language articles
  → template scripts
      content/locales/navigation/assets → TypeScript → Next build → HTTP/SEO verification
```

## 平台边界

Roblox 与 Steam 共用 Basic Info 之后的全部契约：`facts.json` / `evidence.json`、固定语言、Guide Search、site plan、SEO Scout、intake、模板和验收流程都相同。只有必须依赖平台官方数据模型的部分分支：

- Roblox adapter 负责 Place/Universe、创建者、访问量、服务器人数和 Roblox 媒体。
- Steam adapter 负责 App ID、开发商、发行日期、价格、评价、商店功能、系统要求和 Steam 媒体。
- 搜索查询携带平台名用于消歧，首页 hero stats 根据平台事实做确定性映射。

这使平台差异停留在输入适配层，而不是复制两套文章或网站流水线。当前不支持其他商店或主机平台；扩展时必须新增 adapter 并继续输出同一规范事实契约。

## 两个项目内区域

### `intake/`

最终网站输入的唯一事实源，应提交到游戏 Git 仓库。它只包含部署可复现所需内容，不包含密钥、原始网页、LLM debug 或日志。

### `.gamewiki/`

本地工厂工作区，默认被游戏 `.gitignore` 排除：

```text
.gamewiki/
├─ manifest.json
├─ basic-info/
├─ planning/
│  ├─ game-profile.json
│  ├─ guide-search/
│  ├─ site-plan.json
│  └─ seo-keywords.json
├─ content-pipeline/
└─ logs/
```

删除 `.gamewiki` 不影响已经物化的网站，但会失去低成本续跑能力。

## 规划契约

1. `game-profile.json` 由 Basic Info 根据可信游戏事实和平台能力生成，定义允许的分类候选和语义边界。候选词汇可宽于最终导航（最多 16 个），避免在关键词研究前过早淘汰真实类别；最终 site plan 仍最多发布 8 类。Roblox 可把 Codes 作为候选能力，但没有后续证据就不会发布。
2. Guide Search 把搜索关键词和联网研究发现的 `page_opportunities` 合并后审计。知识机会只有在置信度至少 0.72，且拥有一个官方/创作者 URL 或两个不同支持 URL时才能进入聚类；Discord、Reddit、Trello、游戏链接、无实体依据的 Tier List 和工具页会被拒绝。
3. `site-plan.json` 把 Guide Search 主题限制在 profile 内，记录分类顺序、五语言标签与描述、关键词、页面类型、实体/意图元数据、交付数量及状态。`strategy/tips/tactics` 合并到 `guide` 分类但保留独立关键词；planner 不生成无证据的 fallback 主题。

Guide Search 不再把“必须已经出现精确 Suggest 词”作为独立页面的前提。联网研究可以从多个同游戏来源发现有具体玩家意图的系统页和实体页；仍必须通过确定性证据门、Basic Info 语义边界和最终编辑门。这样可以把资料丰富的游戏拆为更多可导航页面，同时继续拒绝完全错误、异义和无支撑主题。

SEO Scout 只接收由 site plan 机械生成的 `seo-keywords.json`。生成阶段按 Codes、Tier List、Update、Entity、Guide 五种页面 brief 控制结构和事实边界；所有形态仍走同一搜索、采集、QA、翻译和 MDX 路由。模板只接收 intake 中 reconcile 后的 site plan。`content/` 是投影，不是反向事实源。

首页也遵循同一所有权：Basic Info 生成 `home.guideSections` 的事实与文案，site plan 决定发布分类；编排器只为已经 published 的分类补 `/<category>` 链接。模板可从 published MDX 确定性生成分类专题卡片，但文章目录不能反向创造首页事实或分类。Hero 使用已处理的真实游戏图片，专题和相关推荐只链接实际存在的页面。

## Checkpoint

- Basic Info：五语言首页、hero、favicon 和验证报告完整才可复用；cache 位于 `.gamewiki/basic-info/.cache/`。
- Guide Search：保留 raw、LLM decision、rejected、manifest 和 keywords。
- Guide Search 的 context checkpoint 同时绑定候选词、YouTube 证据和 Basic Info trusted context 指纹；上游事实或分类边界改变时不能错误复用旧研究判断。
- SEO Scout：搜索、收集、生成、QA、翻译按文件幂等；翻译与英文做结构完整性对照。
- LLM 截断或退化输出不会落盘：英文生成使用独立 token 上限和紧凑降级重试；仅翻译元数据超限时本地压缩后复验正文。
- Template：编排器先按当前 site-plan 把 SEO Scout checkpoint 投影到 intake，再从 intake 重建 content；历史文章可留在 `.gamewiki` 复用，但被淘汰的旧分类不能进入部署项目。

`manifest.json.stages` 记录 generated/reused/migrated/reconciled/failed。日志按 UTC attempt 命名，不覆盖失败现场。

## 发布与 Cloudflare Pages 边界

每个游戏 GitHub 仓库强制为 Private，发布器没有 Public 模式，并在推送前后验证可见性。游戏目录的 `package.json` 位于仓库根，因此 Cloudflare Pages Root directory 留空，Build output directory 固定为 `out`。部署只运行确定性静态 Next.js build；所有 AI 工作在本地工厂完成。

后台站点 Job 默认执行 Private GitHub + Git-integrated Cloudflare Pages 事务：先推送 `main`，再创建/复用严格匹配该 repo 的 Pages 项目、设置 Production `NEXT_PUBLIC_SITE_URL`，触发 Cloudflare 服务端 `npm run build` 并发布 `out` 与 Functions，最后按 deployment ID 和 Git commit 轮询。新任务不得静默回退到 Direct Upload；同名 Direct Upload 或不同 Git source 项目必须阻断。`hosting.status=complete` 表示线上验收通过；`awaiting_domain_configuration` 表示只剩运营者绑定自定义域名/DNS和最终域名验收。模板使用 `/en` 等固定语言前缀；根路径必须 301 到 `/en`，sitemap 的所有 loc/hreflang 必须 self-canonical 且直接返回 200。
