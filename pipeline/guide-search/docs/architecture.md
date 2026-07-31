# 系统架构

## 目标

系统接收一个 Roblox 游戏主题词，输出可供 SEO 内容规划使用的关键词分类。最终结果必须可追溯、可复现，并允许在数据不足时少于 30 个关键词，不能为了数量引入弱相关主题。

## 数据源

|来源|接入方式|主要用途|
|---|---|---|
|DataForSEO Labs|API|长尾词、月搜索量、历史搜索量和搜索意图|
|Google Trends|DataForSEO API|Top、Rising 和相对热度|
|Google Suggest|Google 直连接口；DataForSEO/人工文本备用|真实联想词和长尾表达|
|YouTube|DataForSEO API|视频标题中的玩法和内容主题|
|Similarweb|人工 CSV|补充网页端关键词召回|
|游戏背景|ToAPIs Responses API 联网搜索|确认游戏身份、状态、术语和实体|

不同来源的数值口径保持独立。DataForSEO 月搜索量不能写成 Similarweb 28 天流量，Google Trends 数值不能解释为绝对搜索量。

## 处理流程

```text
游戏主题词 + auto-basic-info 可信身份/玩法事实
   ↓
DataForSEO 自动采集 ─────────────┐
Google Suggest 主词 + a-z ──────┼─→ 标准化、风险过滤、跨源去重
人工 Similarweb / Trends ───────┘
   ↓
ToAPIs Responses API + web_search_preview
   ↓
生成游戏背景、上线状态和术语上下文
   ↓
GPT-5.6 严格 JSON Schema 逐词决策
   ↓
keep / merge / drop + 分类 + 置信度
   ↓
本地硬规则和完整性校验
   ↓
keywords.json
```

## 候选词模型

每个标准化候选词保留：

- 原始关键词和规范关键词；
- 来源集合；
- Labs 搜索量和意图；
- Suggest 排名和出现次数；
- Trends Top/Rising 信号；
- YouTube 播放量和出现次数；
- 原始证据；
- 本批次综合排序分。

综合分只决定候选词处理顺序，不直接决定最终保留。最终语义判断由 LLM 完成，本地硬规则拥有最终否决权。

## 人工输入契约

人工文件位于：

```text
input/<游戏slug>/
├─ similarweb.csv
└─ google-suggest.txt
```

`similarweb.csv` 识别 `keyword`、`query`、`search term`、`关键词` 等常用列名。`google-suggest.txt` 每行一个完整关键词。两类输入都经过与自动数据相同的标准化、风险过滤和去重流程。

默认 `suggest_source=auto`：直接访问 `suggestqueries.google.com`，依次采集主词与 a–z，共 27 次。人工 Suggest 只在显式 `manual` 模式使用，DataForSEO 是显式备用。逐请求结果和去重列表写入 `raw/autocomplete.json`。

## LLM 阶段

### 游戏背景研究

- 接口：ToAPIs `/v1/responses`
- 默认模型：`gemini-2.0-flash-official`
- 工具：`web_search_preview`
- 必须在响应中检测到 `web_search_call`
- 输出：游戏类型、发布状态、实体、术语、来源和警告

### 关键词聚类

- 接口：ToAPIs `/v1/chat/completions`
- 默认模型：`gpt-5.6-terra`
- 输出约束：strict JSON Schema
- 每个输入候选词必须恰好出现一次
- 允许操作：`keep`、`merge`、`drop`
- `merge_into` 必须是现有候选词，不能创造新词

## 最终硬规则

- 最多 40 个关键词、8 个分类；不强制补足分类。简单游戏接受更少，资料丰富的游戏保留不同玩家意图和具体实体页，不能为旧的 3–5 篇经验值过度合并。
- `codes` 最多一个关键词。
- 低于 `0.55` 置信度自动排除；上游基础信息可提升同游戏主题的事实可信度。
- 只有 YouTube 证据不是自动排除理由，仍由具体性、搜索价值和游戏背景决定。
- Reddit、Discord、Trello 不允许成为独立文章。
- Logo、YouTube、game link 一律排除。
- script、hack、exploit、pastebin、auto farm 等风险意图一律排除。
- 分类名通常为一个小写英文单词，`tier list` 是允许的例外。
- release date 根据发布状态和持续搜索价值决定保留、合并或排除。
- 最终关键词必须来自候选集，必须以规范主题词开头并保持 ASCII。
- 分类之间允许少量信息重叠，但异游戏、同名歧义和完全无关内容必须排除。

## 输出契约

`keywords.json`：

```json
{
  "topic_name": "anime expeditions",
  "categories": [
    {
      "category": "codes",
      "keywords": ["anime expeditions codes"]
    }
  ]
}
```

审计产物：

- `candidates.json`：所有规范候选词和证据；
- `manual-input.json`：人工输入读取统计；
- `keywords-rules.json`：不使用 LLM 的规则基线；
- `llm/game-context.json`：联网背景；
- `llm/cluster-decisions.json`：逐词决定；
- `llm/rejected.json`：LLM 和硬规则排除原因；
- `manifest.json`：来源数量、DataForSEO 成本、ToAPIs token 和验证结果。

## 缓存和费用

- DataForSEO 原始响应写入 `raw/`。
- `--from-run` 复用 `raw/`，但默认重新调用 ToAPIs。
- `--cluster-mode rules` 可以完全离线重分类。
- 单个付费 POST 请求不做隐式重试。
- DataForSEO 使用响应中的真实 `cost`；ToAPIs 只记录 token，美元金额以控制台为准。

## 失败策略

- 单个 DataForSEO 来源失败时记录错误并继续其他来源。
- 人工文件格式错误时任务失败并指出文件和缺少的列。
- 强制 `--suggest-source manual` 但文件不存在时，在付费采集前失败。
- ToAPIs 联网响应缺少 `web_search_call` 时失败。
- LLM 漏词、重复词或返回未知词时验证失败，不发布不完整结果。
- 最终 Schema 或业务规则失败时不把结果视为成功。
