# AI / 开发者接手说明

SEO Scout 负责 search、collect、generate、语义 QA 和 translate，不负责决定站点语言或分类。

## 编排契约

- 输入必须是 planner 从 `site-plan.json` 机械生成的 `seo-keywords.json`。
- 编排器通过 `python -m seoscout --project-dir <exact-dir> run ...` 指定真实项目目录。
- 设置 `--project-dir` 后，所有 `out/`、`logs/`、`articles/` 和缓存只能写入该目录，不能写回源码仓库 `projects/`。
- 目标语言固定由输入给出 `es/de/fr/ja/ko`；英文是生成源语言。
- QA 是必经步骤。被判定文不对题的英文和翻译必须一起删除并保留审计日志。
- 已存在且有效的搜索、素材、文章和翻译默认跳过；只有显式 `--overwrite` 才重做付费工作。

修改路径或幂等逻辑后，至少运行 Python 编译检查，并通过根编排器的端到端项目测试。
