# get-search

输入一个 Roblox 游戏名，自动采集搜索需求、合并可选的人工数据，并输出经过联网语义聚类和硬规则审计的 SEO 关键词集合。

项目的最终交付物是每次运行目录中的 `keywords.json`。其他 JSON 和 Markdown 文件用于追踪来源、检查模型决策和定位问题。

## 快速开始

要求：Python 3.11 或更高版本。项目只使用 Python 标准库，不需要安装额外依赖。

凭据统一填写在 `game-wiki-factory/.env`，由根编排器传入本模块：

```dotenv
dataforseo_name=your_dataforseo_login
dataforseo_password=your_dataforseo_password
TOAPIS_KEY=your_toapis_key
```

不要在本模块目录维护第二份 `.env`。日常从 factory 根目录使用 `python gamewiki.py --config ...`；直接调试 `main.py` 时需先把根 `.env` 加载到当前进程。

运行一个新游戏：

```powershell
python main.py "Anime Expeditions"
```

程序默认执行：

1. 通过 DataForSEO 获取 Labs、Google Trends 和 YouTube 数据。
2. 直接调用 Google Suggest，采集主词和 a–z 联想。
3. 自动读取 `input/<游戏slug>/` 中存在的 Similarweb 和 Google Trends 人工数据。
4. 通过 ToAPIs 联网研究游戏背景、上线状态和专有名词。
5. 对每个候选词执行保留、合并或排除，再通过硬规则审计生成 `output/<游戏slug>-<UTC时间>/keywords.json`。

## 每个新游戏的标准流程

假设游戏名为 `Anime Expeditions`，对应 slug 为 `anime-expeditions`。

### 1. 准备可选的人工数据

创建目录：

```text
input/anime-expeditions/
```

可以放入：

```text
input/anime-expeditions/
├─ similarweb.csv                         # 可选
├─ searched_with_top-searches_*.csv       # 可选，Google Trends 导出
├─ searched_with_rising-searches_*.csv    # 可选，Google Trends 导出
└─ google-suggest.txt                     # 可选，仅 manual 模式使用
```

两个文件都不是必需的。缺少时程序继续使用自动数据源。

### 2. 执行

```powershell
python main.py "Anime Expeditions"
```

### 3. 检查结果

优先查看：

```text
keywords.json                 最终关键词
report.md                     人类可读摘要
llm/cluster-decisions.json    每个候选词的决定和理由
llm/rejected.json             最终排除原因
manual-input.json             人工文件读取统计和无效行
manifest.json                 数据源、费用、模型和 token 用量
```

## 如何提供 Similarweb 数据

从 Similarweb 导出关键词 CSV 后：

1. 将文件重命名为 `similarweb.csv`。
2. 放到对应游戏目录，例如 `input/anime-expeditions/similarweb.csv`。
3. 保留关键词列即可，分组、标签和排序不会影响读取。

程序支持以下关键词列名：

```text
keyword
keywords
query
search term
search keyword
关键词
關鍵詞
```

只有一列且没有表头的 CSV 也能读取。推荐格式：

```csv
关键词
anime expeditions codes
anime expeditions release date
unit (anime expeditions)
```

模板见 `input/_example/similarweb.csv`。

Similarweb 词会标记为 `similarweb` 来源，与 DataForSEO 和其他来源去重合并。原始月搜索量口径不会被伪装成 Similarweb 的 28 天流量。

同一输入目录也支持直接放入 Google Trends 导出的相关搜索 CSV，文件名保持下载时的格式即可：

```text
searched_with_top-searches_*.csv
searched_with_rising-searches_*.csv
```

程序读取 `query` 和 `search interest` 列，分别记录为手动 Trends Top/Rising 信号，并与其他来源去重合并。与游戏主题无关的相关查询仍会经过统一风险过滤和 LLM 聚类，不会因为来自 Trends 就自动进入最终结果。

如果在自动采集完成后才补充 Similarweb 文件，可以复用原始数据重新聚类：

```powershell
python main.py --from-run output\anime-expeditions-20260716T112902Z
```

这不会重新请求 DataForSEO，但会重新调用 ToAPIs。只想免费检查人工词是否被读取，可运行：

```powershell
python main.py --from-run output\anime-expeditions-20260716T112902Z --cluster-mode rules
```

## Google Suggest 方案

Google Suggest 是每个游戏的默认必备流程。程序直接请求：

```text
https://suggestqueries.google.com/complete/search?client=firefox&q=<关键词>
```

程序先查询一次游戏主词，再查询主词加 `a`–`z`，共 27 次；结果去重后进入候选池。该接口不需要 API Key，采集成本为 0。每次运行会在 `raw/autocomplete.json` 保存 endpoint、查询 URL、原始联想和单次错误，方便审计。

|场景|做法|
|---|---|
|正常自动化|直接 Google Suggest，主词 + a–z|
|低成本试跑|只请求主词，不遍历 a-z|
|已有人工 Suggest|提供 `google-suggest.txt`，并显式使用 `manual` 模式|
|直接接口暂时不可用|显式切换到 DataForSEO|

默认模式为 `auto`，每次都直接请求 Google Suggest。人工文件只在显式指定 `--suggest-source manual` 时替代直接请求；DataForSEO 不再是默认 Suggest 来源。

人工文件格式为每行一个完整联想词：

```text
anime expeditions codes
anime expeditions tier list
anime expeditions release date
```

以 `#` 开头的行会被忽略。模板见 `input/_example/google-suggest.txt`。

相关命令：

```powershell
# 推荐：每次直接采集 Google Suggest
python main.py "Anime Expeditions" --suggest-source auto

# 强制直接 Google Suggest，并采集主词 + a-z
python main.py "Anime Expeditions" --suggest-source google --autocomplete-prefixes az

# 强制 DataForSEO，并采集主词 + a-z
python main.py "Anime Expeditions" --suggest-source dataforseo --autocomplete-prefixes az

# 强制 DataForSEO，但只查主词
python main.py "Anime Expeditions" --suggest-source dataforseo --autocomplete-prefixes none

# 强制人工文件；文件不存在会立即报错，不会产生 Suggest API 费用
python main.py "Anime Expeditions" --suggest-source manual
```

历史样本中，主词加 a-z 的 DataForSEO Suggest 成本约为 `$0.042–$0.054`/游戏，仅供估算；实际价格以 DataForSEO 返回的 `cost` 为准。

## 重新运行与局部刷新

复用已有 DataForSEO 原始数据并重新联网聚类：

```powershell
python main.py --from-run output\existing-run
```

完全离线的规则基线：

```powershell
python main.py --from-run output\existing-run --cluster-mode rules
```

只刷新一个付费数据源：

```powershell
python main.py --from-run output\existing-run --refresh-source youtube
python main.py --from-run output\existing-run --refresh-source autocomplete --suggest-source dataforseo
```

`--refresh-source` 可重复指定。程序不会对付费 POST 请求做隐式重试。

## 输出目录

```text
output/<slug>-<UTC时间>/
├─ raw/
│  ├─ labs.json
│  ├─ trends.json
│  ├─ autocomplete.json
│  └─ youtube.json
├─ llm/
│  ├─ game-context.json
│  ├─ context-response.json
│  ├─ cluster-decisions.json
│  ├─ cluster-response.json
│  └─ rejected.json
├─ candidates.json
├─ manual-input.json
├─ keywords-rules.json
├─ keywords.json
├─ manifest.json
└─ report.md
```

ToAPIs 返回 token 用量但不返回美元金额，因此实际 LLM 费用以 ToAPIs 控制台为准。

## 关键词审计规则

- 最多 40 个关键词和 8 个分类，但资料不足时允许少于 30 个。
- 分类和文章只来自可审计的同游戏证据，不设强制最低数量。简单游戏可以更少；资料丰富的游戏应保留不同玩家意图和具体实体页，不能因旧的 3–5 篇经验值而过度合并。
- `codes` 最多保留一个词。
- Reddit、Discord、Trello 不生成独立文章。
- Logo、YouTube 导航词、game link 一律排除。
- 只有 YouTube 证据不是淘汰理由；仍按主题具体性、搜索价值和游戏背景判断。
- LLM 置信度低于 `0.55` 排除；上游 `auto-basic-info` 的官方身份和已验证内容可作为同游戏证据。
- 不同攻略分类允许少量内容重叠，但完全不相关或属于其他游戏的同名词必须排除。
- script、hack、exploit、pastebin、auto farm 等风险意图排除。
- release date 根据游戏状态和持续搜索价值判断，不机械删除。
- LLM 不能创造候选集中不存在的新关键词。

完整编排器会把 `auto-basic-info` 产出的官方游戏 URL 和站点内容写入可信上下文，随后通过 `--trusted-context-file` 传给本模块。这能避免新游戏因搜索量不足而把官方已确认的玩法、升级、敌人等主题误删。

## 项目结构

|路径|职责|
|---|---|
|`main.py`|命令行入口|
|`get_search/cli.py`|参数解析|
|`get_search/config.py`|`.env` 和运行设置|
|`get_search/collectors.py`|DataForSEO、Google Suggest 和 YouTube 采集|
|`get_search/manual_inputs.py`|Similarweb、Google Trends 和人工 Suggest 导入|
|`get_search/classifier.py`|候选词标准化、规则基线和校验|
|`get_search/llm_cluster.py`|ToAPIs 联网研究、结构化聚类和硬过滤|
|`get_search/pipeline.py`|完整流程编排和产物写入|
|`tests/`|单元测试|
|`docs/architecture.md`|架构、字段和约束说明|

## 测试

修改代码后至少执行：

```powershell
python -m compileall -q get_search tests
python -m unittest discover -s tests -v
```

需要验证真实联网链路时，复用一个已有运行目录，避免再次请求 DataForSEO：

```powershell
python main.py --from-run output\anime-expeditions-20260716T112902Z
```
