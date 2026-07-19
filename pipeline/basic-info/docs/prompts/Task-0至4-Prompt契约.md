# Task 0–4 Prompt 契约（设计稿）

本文不是最终业务代码，而是 API 调用时必须遵守的输入、输出和禁止项。所有模型输出先验证，验证失败不得直接写入网站。

## 全局规则

- 第一版只支持 Roblox，用户输入只有游戏名。
- 已由 Roblox API 确认的事实不得被联网模型覆盖。
- 找不到信息时输出 `missing`，不得补写看似合理的 URL、兑换码、日期或数字。
- 搜索摘要只能作为线索，不能单独把事实提升为 `verified`。
- 事实必须引用 `sourceRefs`；纯文案不伪装成事实。
- 模型只输出 JSON，不输出 Markdown 代码围栏或“自查通过”等说明。
- 运行时结构以 `src/gamewiki_automation/schemas.py` 中的 RESEARCH/HOMEPAGE/MODULES Schema 为准；最终输出分别写入 facts、evidence、首页配置、模块和验证报告。

## Task 0：同名游戏消歧

触发条件：Roblox Discover 得到多个近似候选，或候选置信度未达到自动选择阈值。

输入：用户游戏名，以及每个候选的名称、Place ID、创建者、描述、访问量和 Roblox URL。

模型职责：只比较候选，不重新发明候选；优先名称完全匹配、当前可访问、描述主题一致和可信创建者。旧 Place、搬迁页和同名仿制品必须列为排除项。

输出：

```json
{
  "selectedPlaceId": "string|null",
  "confidence": 0.0,
  "reason": "string",
  "rejected": [{ "placeId": "string", "reason": "string" }],
  "requiresHumanReview": false
}
```

自动通过条件：`confidence >= 0.85` 且只有一个合理候选；否则停止并保留候选清单。

## Task 1：Roblox 官方事实

Task 1 不调用 LLM。程序通过 Place→Universe、Games、Group/Creator、Thumbnails 等 Roblox 公共接口填充 `facts.identity`、`facts.roblox` 和官方媒体候选，并记录采集时间。接口失败时保留缺失状态，不能用搜索摘要代填动态数值。

## Task 2：外部资源联网研究

默认 API：ToAPIs `POST /v1/responses`，模型 `gpt-5.3-codex-official`，工具 `web_search_preview`。Perplexity sonar 仅在 ToAPIs 联网调用失败时降级使用。OpenRouter 与 Tavily 均不调用。

输入：游戏名、已确认 Roblox URL/Place/Universe/创建者/描述，以及当前缺失字段清单。

只研究以下内容：创建者官网或 Linktree、官方 Discord/X/YouTube/TikTok、官方 Trailer、可验证兑换码、可验证语言线索。不要生成首页文案。

来源优先级：Roblox/创建者官方页 > 官方账号平台页 > 可信第三方 > 社区页 > 搜索摘要。第三方代码只能标记为 `reported` 或 `unknown`，不能标记为官方有效。

输出：只返回 `facts.officialLinks`、`facts.media`、`facts.codes`、`facts.languages` 的补丁，以及新增 `evidence[]`。每个非空事实至少引用一个 source id；URL 必须来自实际访问或搜索结果，不得按账号名猜测。

## Task 3：首页配置生成

Task 3 默认不联网，只读取已验证的 `facts` 和 `evidence`。输出英文首页配置 `homepage`。

硬性要求：

- `metaTitle` 30–60 字符，`metaDescription` 120–160 字符；
- Hero 固定 5 个 stats，每个通过 `factPath` 指回事实；
- Hero 图片最多 5 张，只能使用已验证 URL；
- 固定 4 张 Start cards；
- 语言 1–4 门，不足时不凑数；
- Sidebar codes 最多 2 条，无可靠代码时允许空数组；
- CTA 优先官网，官网缺失时使用 Roblox 游戏页；
- HSL 颜色必须可解析，理由属于设计判断而不是游戏事实；
- favicon 只生成图像 Prompt，不声称已经生成文件。

禁止：改变 Place ID/URL、添加新事实、引用未进入 evidence 的链接、把推断写成官方结论。

## Task 4：首页模块规划

输入：`facts`、`evidence` 与首页配置。输出 4–8 个模块，每个模块必须属于 `codes`、`guide`、`tier-list`、`faq` 之一。

模块数量由可靠资料决定，不强制凑满 8 个。Tier List 若缺少足够的版本化资料，只能标记 `editorial-draft` 或不生成；不得把模型偏好伪装成社区共识。Codes 模块允许呈现“暂无已验证代码”。

## Task 5–6（非研究模型职责）

- Task 5 下载并验证媒体尺寸、类型、HTTP 状态，随后独立生成 favicon 资产。
- Task 6 执行 JSON Schema、URL、来源引用、字符长度、动态字段时间戳及事实冲突校验。
- 任一核心身份错误、Schema 错误或核心 URL 无效均为 `fail`；证据不足但可生成草稿为 `warning`。

## 两个样本的专项断言

Anime Expeditions 必须选择 Place `84515722934860`，不得因搜索召回差而判定没有 Roblox 页面。

PursuitCore 必须选择 Place `121903154323395`，并把旧链接或同名候选作为已排除候选记录，不能混合两个 Place 的动态数据。
