# AI / 开发者接手说明

本项目是 Roblox SEO 关键词研究工具，最终交付物是每次运行目录中的 `keywords.json`。它与首页资料、图片和站点模板生成项目相互独立。

## 首次接手

1. 完整阅读 `README.md` 和 `docs/architecture.md`。
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
- 低于 0.75 置信度、风险意图和含义残缺的主题仍应排除。
- 不为数量创造候选词；LLM 只能 keep、merge、drop 已有候选。
- `keywords.json` 最多 40 个词、8 个分类，但允许少于 30 个，分类没有最少词数。
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
