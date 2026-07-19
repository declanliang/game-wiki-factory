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
2. `site-plan.json` 把 Guide Search 关键词限制在 profile 内，记录分类顺序、六语言标签、关键词、交付数量及状态。

SEO Scout 只接收由 site plan 机械生成的 `seo-keywords.json`。模板只接收 intake 中 reconcile 后的 site plan。`content/` 是投影，不是反向事实源。

## Checkpoint

- Basic Info：六语言首页、hero、favicon 和验证报告完整才可复用；cache 位于 `.gamewiki/basic-info/.cache/`。
- Guide Search：保留 raw、LLM decision、rejected、manifest 和 keywords。
- SEO Scout：搜索、收集、生成、QA、翻译按文件幂等；翻译与英文做结构完整性对照。
- Template：从 intake 重建 content，防止已删除文章或旧分类残留。

`manifest.json.stages` 记录 generated/reused/migrated/reconciled/failed。日志按 UTC attempt 命名，不覆盖失败现场。

## Vercel 边界

游戏目录的 `package.json` 位于仓库根，因此 Vercel Root Directory 留空。部署只运行确定性 Next.js build；所有 AI 工作在本地工厂完成。正式部署必须设置 `NEXT_PUBLIC_SITE_URL`。
