# Game Wiki Factory 架构

## 仓库边界

`game-wiki-factory` 是控制面和全部通用源码的唯一 Git 仓库。具体游戏是独立的数据面和部署仓库：

```text
Games/
├─ game-wiki-factory/       通用代码、模板、契约、测试、文档
├─ hellhole/                独立 Next.js/GitHub/Vercel 项目
└─ another-game/            独立 Next.js/GitHub/Vercel 项目
```

工厂不保存真实游戏 output。游戏仓库不保存 API key，也不在 Vercel 调用搜索或 LLM。

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
游戏名
  → pipeline/basic-info
      官方身份、事实、首页、hero/favicon、固定六语言、category candidates
  → pipeline/guide-search
      Google Suggest 主词+a–z、DataForSEO、搜索意图、语义聚类与淘汰审计
  → planner / project_contract.py
      game-profile + keywords → site-plan
  → pipeline/seo-scout
      search → collect → generate → topic QA → translate
  → intake
      identity + site content + site plan + assets + 6-language articles
  → template scripts
      content/locales/navigation/assets → TypeScript → Next build → HTTP/SEO verification
```

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

1. `game-profile.json` 由 Basic Info 根据可信游戏事实生成，定义允许的分类候选和语义边界。
2. `site-plan.json` 把 Guide Search 关键词限制在 profile 内，记录分类顺序、六语言标签与描述、关键词、交付数量及状态。`strategy/tips/tactics` 合并到 `guide` 分类但保留独立关键词；planner 不生成无搜索证据的 fallback 关键词。

SEO Scout 只接收由 site plan 机械生成的 `seo-keywords.json`。模板只接收 intake 中 reconcile 后的 site plan。`content/` 是投影，不是反向事实源。

首页也遵循同一所有权：Basic Info 生成 `home.guideSections` 的事实与文案，site plan 决定发布分类；编排器只为已经 published 的分类补 `/<category>` 链接。文章目录不能反向创造首页事实或分类。

## Checkpoint

- Basic Info：六语言首页、hero、favicon 和验证报告完整才可复用；cache 位于 `.gamewiki/basic-info/.cache/`。
- Guide Search：保留 raw、LLM decision、rejected、manifest 和 keywords。
- SEO Scout：搜索、收集、生成、QA、翻译按文件幂等；翻译与英文做结构完整性对照。
- LLM 截断或退化输出不会落盘：英文生成使用独立 token 上限和紧凑降级重试；仅翻译元数据超限时本地压缩后复验正文。
- Template：从 intake 重建 content，防止已删除文章或旧分类残留。

`manifest.json.stages` 记录 generated/reused/migrated/reconciled/failed。日志按 UTC attempt 命名，不覆盖失败现场。

## 发布与 Vercel 边界

每个游戏 GitHub 仓库强制为 Private，发布器没有 Public 模式，并在推送前后验证可见性。游戏目录的 `package.json` 位于仓库根，因此 Vercel Root Directory 留空。部署只运行确定性 Next.js build；所有 AI 工作在本地工厂完成。

发布器只连接 Private GitHub repo 与 Vercel project，不拥有正式域名决策权，也不写 Vercel 环境变量。站点负责人绑定最终域名并填写 `NEXT_PUBLIC_SITE_URL` 后再完成生产验证。模板集中把裸域名规范为 HTTPS origin，并让 metadata、JSON-LD、sitemap 与 robots 共享 locale-aware URL 构造器；非英语页面必须 self-canonical。部署验收拒绝重定向 sitemap URL、域名后双斜杠、canonical/hreflang 冲突和 metadata 缺失。
