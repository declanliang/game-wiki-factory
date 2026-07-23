# AI / 开发者接手说明

SEO Scout 负责 search、collect、generate、语义 QA 和 translate，不负责决定站点语言或分类。

## 编排契约

- 输入必须是 planner 从 `site-plan.json` 机械生成的 `seo-keywords.json`。
- 编排器通过 `python -m seoscout --project-dir <exact-dir> run ...` 指定真实项目目录。
- 设置 `--project-dir` 后，所有 `out/`、`logs/`、`articles/` 和缓存只能写入该目录，不能写回源码仓库 `projects/`。
- 目标语言固定由输入给出 `es/de/fr/ja`；英文是生成源语言。
- QA 是必经步骤。被判定文不对题的英文和翻译必须一起删除并保留审计日志。
- `seo-keywords.json.topic_specs` 可声明 Codes、Tier List、Update、Entity 或 Guide；生成器必须应用对应页面 brief，但搜索/采集/QA/翻译路径保持一致并兼容旧的纯字符串关键词。
- 一个页面只解决一个主要玩家意图。Codes 不得编造代码，Tier List 不得编造实体或数据，Update 不得编造版本日期，Entity 页不得膨胀成全游戏总攻略；Calculator 等工具页不在本阶段。
- 已存在且有效的搜索、素材、文章和翻译默认跳过；只有显式 `--overwrite` 才重做付费工作。
- 翻译完成后必须运行确定性的本地标题消歧；不同 source slug 不得因译成同一泛化标题而留下重复 SEO title。该修复只改 metadata title，不重写正文。

修改路径或幂等逻辑后，至少运行 Python 编译检查，并通过根编排器的端到端项目测试。
