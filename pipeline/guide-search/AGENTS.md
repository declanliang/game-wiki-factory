# AI / 开发者接手说明

本模块是 Game Wiki Factory 的 Roblox SEO 关键词研究阶段，最终交付物是游戏 `.gamewiki/planning/guide-search/keywords.json`。

## 首次接手

1. 完整阅读本模块 `README.md` 和 Factory 根目录 `docs/HANDOFF.md`。
2. 运行离线检查：

```powershell
python -m compileall -q get_search tests
python -m unittest discover -s tests -v
```

3. 查看 `get_search/pipeline.py` 理解编排，查看 `get_search/classifier.py` 和 `get_search/llm_cluster.py` 理解候选与聚类规则。
4. 不要为了试验直接运行新游戏；DataForSEO 和 ToAPIs 会产生费用。优先使用测试，或用已有 `output/` 配合 `--from-run --cluster-mode rules`。

## 不能破坏的规则

- 不读取、打印、复制或提交 `.env` 的值。
- 不提交 `output/` 或 `input/<真实游戏>/`；只提交 `input/_example/`。
- 默认 Google Suggest 必须直接请求 `suggestqueries.google.com`，执行主词加 a–z 共 27 次；DataForSEO Suggest 只作显式备用。
- Similarweb 和 Google Trends 网页导出保持人工导入，不伪造其数值口径。
- Reddit、Discord、Trello、Logo、YouTube 导航词和 game link 不生成独立文章。
- “只有 YouTube 证据”不是淘汰理由；应按具体性、搜索价值和游戏背景判断。
- 低于 0.55 置信度、风险意图和含义残缺的主题仍应排除；上游基础信息是可信的同游戏证据。
- 不为数量创造候选词。联网 context 阶段可提出带证据的 `page_opportunities`；通过确定性证据门后，聚类 LLM 只能 keep、merge、drop 或在 profile 内重分类现有候选。
- `keywords.json` 最多 40 个词、8 个分类；简单游戏允许更少，资料丰富的游戏应保留不同玩家意图和具体实体页，禁止为数量合成候选，也禁止为旧的 3–5 篇经验值过度合并。
- Page opportunity 需要置信度至少 0.72，以及一个官方/创作者 URL 或两个不同支持 URL；必须记录 pageType、实体/意图和 provenance。Calculator/Planner/Team Builder 不进入候选。
- 单个娱乐/挑战视频不能创建推断主题；juking、movement、passing、map positioning 等机制必须由至少两个不同视频共同支持，之后仍需 LLM 语义门判断。
- 联网 context 接收去重后的 YouTube 标题和 URL。Roster/collection 游戏中，同一命名实体至少有两个不同视频支持，或有一个官方/创作者来源，才可提出独立 entity page；不能只生成总览页而丢掉已满足门槛的实体。
- 编排模式必须支持 `--run-dir <project>/planning/guide-search`；不要把真实游戏输出写回源码仓库的 `output/`。
- 下游分类边界来自 Basic Info 的 game-profile。Profile 可包含最多 16 个允许候选，Guide Search 提议和排序关键词，但最终 site-plan 不能接纳 profile 之外的分类且最多发布 8 类。
- 攻略分类允许少量内容重叠；不能因为重叠就把不同的玩家信息需求全部合并。
- 修改 Prompt、过滤规则、输入格式或输出契约后必须增加/更新测试并跑完整测试集。

## 代码地图

|路径|职责|
|---|---|
|`main.py`|命令行入口|
|`get_search/cli.py`|参数解析|
|`get_search/config.py`|`.env` 与运行设置|
|`get_search/collectors.py`|DataForSEO、Google Suggest 与 YouTube 采集|
|`get_search/manual_inputs.py`|Similarweb、Google Trends 和人工 Suggest 导入|
|`get_search/classifier.py`|标准化、召回合并、规则分类和输出校验|
|`get_search/llm_cluster.py`|ToAPIs 联网背景研究与逐词聚类|
|`get_search/pipeline.py`|流程编排、费用和产物写入|
|`tests/`|离线单元测试|

## 修改后的最低验收

```powershell
python -m compileall -q get_search tests
python -m unittest discover -s tests -v
```

验收要求：所有测试通过；不得出现密钥、真实人工输入或运行输出进入 Git 变更；涉及真实 API 的验证要在交付说明中列出调用来源和费用。
