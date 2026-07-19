# ToAPIs Responses API 迁移验证

验证日期：2026-07-17

## 结论

OpenRouter 已从项目运行链移除。主调用改为：

```text
POST https://toapis.com/v1/responses
model: gpt-5.3-codex-official
web tool: web_search_preview
```

Perplexity `sonar-pro` 只保留为联网任务的失败降级路径；非联网首页生成也使用 ToAPIs Responses。

参考文档：

- https://docs.toapis.com/docs/cn/api-reference/chat/responses
- https://docs.toapis.com/docs/cn/api-reference/chat/models
- https://docs.toapis.com/docs/cn/api-reference/chat/list-models

## 为什么不用 gpt-5.5 联网

当前 Key 的 `/v1/models` 返回：

|模型|端点元数据|选择|
|---|---|---|
|`gpt-5.3-codex-official`|包含 Responses/OpenAI 端点|文档明确用它演示 `web_search_preview`，作为默认联网模型|
|`gpt-5-pro-official`|包含 Responses/OpenAI 端点|可作为后续候选，尚未做联网探针|
|`gpt-5.5`|普通 OpenAI 端点|不用于联网，也不作为当前 Responses 默认值|

项目将非联网与联网模型拆成 `TOAPIS_MODEL`、`TOAPIS_WEB_MODEL`，避免将不支持内置搜索工具的模型误用于 Task 2/4。

## 实测

### 联网探针

请求要求搜索 Anime Expeditions 的官方 Roblox URL。响应：

```text
status: completed
requested model: gpt-5.3-codex-official
output types: reasoning, web_search_call, reasoning, web_search_call, reasoning, message
result: https://www.roblox.com/games/84515722934860/Anime-Expeditions
```

说明 Responses 输出不能假设第一项就是文本；客户端必须遍历 `output[]`，只提取 `message.content[].output_text`。

### JSON 管线探针

通过项目新 `LlmClient` 执行小型、非联网 Schema 请求：

```text
toapis-json-smoke: PASS
schemaRepaired: false
retriedMalformed: false
```

证明 Schema 进入 Prompt、Responses 文本提取、JSON 解析和本地 JSON Schema 强校验可以连通。

## 当前限制

- ToAPIs 文档没有说明 `web_search_preview` 的搜索次数或结果数量硬上限。
- 响应提供 token usage，但没有承诺提供美元费用字段。
- 当前只完成小额真实探针；两个完整样本尚未在 ToAPIs 上执行三任务 `--refresh`。
- ToAPIs 文档未列出 Responses 的结构化输出参数，因此项目不依赖网关声明格式正确：Schema 明文加入 Prompt，返回后本地强校验，失败时用无联网修复请求处理。
