# 已知问题与后续建议

更新时间：2026-07-18

## P0：目前没有已知的代码级阻断

OpenRouter 已从配置、客户端和降级链移除。ToAPIs 当前 Key 的模型列表查询、Responses API 和 `gpt-5.3-codex-official + web_search_preview` 联网探针均通过；23 项自动化测试和模板真实消费者测试通过。

现有 Anime Expeditions 与 PursuitCore 已包含 LANGUAGES 对应的本地化首页文件；缓存完整时可离线重新导出完整模板包。

## P1：建议在正式批量生产前处理

### 1. 官方社群所有权验证仍不完全自动化

当前流程由 GPT 联网寻找 Discord、YouTube、X、TikTok 和官网，再检查 URL 是否可访问。HTTP 可访问只能排除明显死链，不能百分之百证明账号属于开发者。

影响：同名游戏或社区仿冒账号可能被误判为官方。

建议：增加“Roblox 游戏页/创建者 Linktree/官网必须直接链接该社群”的关系图；无法形成官方链接链条时降为 `supported`，而不是 official。

### 2. ToAPIs 迁移后尚未付费重跑完整双样本

ToAPIs 已完成真实联网探针与 Responses 输出解析测试，但 Anime Expeditions、PursuitCore 的三任务完整 LLM 产物是迁移前生成的数据，目前只做了迁移后的离线 Schema/模板回归。

影响：ToAPIs 在超长 Prompt、复杂 Schema 或连续三任务下的费用、耗时与 JSON 稳定性还缺少最终实测；Perplexity 降级路径也未重新跑完整双样本。

2026-07-17 Anime Expeditions 完整刷新中，Task 2 的 ToAPIs 调用失败并自动降级为 Perplexity，Task 3/4 使用 ToAPIs 成功。旧实现没有把主调用失败原因写入 fallback meta；现已补充 `fallbackFrom`，但本次已经完成的调用无法追溯具体错误文本。

建议：API 预算允许时对两个样本执行一次 `--refresh`，重点检查 `schemaRepaired`、`retriedMalformed`、`webSearchCalls` 和最终事实质量。

### 3. 没有真正的美元硬预算熔断

当前通过低 reasoning、超时和缓存控制费用，但 ToAPIs 文档没有为 `web_search_preview` 提供可用的搜索结果数量上限。程序只能在响应完成后读取 token usage；网关当前响应也未承诺返回美元费用。

影响：疑难游戏的单次研究费用仍可能超过目标。

语言市场任务需要在一次调用中检查 8 个候选语言，ToAPIs 曾多次返回 HTTP 524；程序能自动降级到 Perplexity，但会增加延迟，且 ToAPIs 失败请求是否产生网关侧费用无法从失败响应判断。

进展：Factory 新站已固定只生成 `en/es`，不再为 `de/fr/ja` 支付默认翻译成本。其他语言市场判断已移交上线后的 Growth Agent，根据 GSC/GSA 查询语言、国家、排名页面和用户批准单独扩展；Basic Info 不再调用语言市场调研 API。

### 4. 已通过内容导入，但尚未完成整站构建与页面验收

当前已经在隔离副本中用最新版 `check-intake.mjs + apply-content.mjs + apply-locales.mjs` 导入 Anime Paradox X：语言声明、英文首页和西班牙语首页均成功写入，0 error、0 warning，模板原仓库未修改。

尚未覆盖 `new-site.env` 全量生成、素材复制、文章接入、`launch:site`、Next.js build 和页面截图。

建议：下一阶段增加“生成 → 创建站点副本 → 写入 intake/env/assets → launch:site → build → 页面截图”的验收。

## P2：可以后续优化

### 5. 身份搜索依赖 Jina Reader

Roblox Discover 的公开结果通过 Jina Reader 获取。Reader 或 Roblox 页面结构变化会导致身份发现失败。

当前行为是安全失败，不会猜 Place ID。

建议：增加第二条身份来源，例如 Roblox 官方搜索接口（若有稳定认证方案）或 ToAPIs 只用于候选发现、Roblox API 用于最终确认。

### 6. favicon 是官方图标转换，不是原创品牌设计

程序会把 Roblox 官方游戏图标转换为全尺寸 favicon 包，并输出 AI 绘图 Prompt。

影响：技术上可直接使用，但视觉上可能不如专门设计的 Wiki favicon，也应确认品牌素材使用方式。

建议：接入独立图片生成模型作为可选 Task 5B，生成后仍保留人工审核。

### 7. 动态内容存在自然过期

在线人数、访问量、更新日期、兑换码和游戏版本都会变化。缓存已经设置 TTL，但已经导入网站的静态内容不会自动更新。

当前首页生成缓存包含动态统计值：Roblox 缓存过期后，如果在线人数发生变化，即使长期文案没有变化，也会重新调用首页生成模型。这样能保持 Hero stats 新鲜，但频繁批处理会增加费用。

多语言版本会放大这一影响：英文 `site-content.json` 的 Hero stats 或首页生成文案变化后，对应的 `homepage_locale_<locale>` 缓存键也会变化，需要重新生成该语言文件。2026-07-18 的 Anime Paradox X 复跑中，研究与模块任务命中缓存，但 `homepage_config` 和 `homepage_locale_es` 因上游内容变化重新调用；ToAPIs 未返回美元费用，因此不能声称该轮为零成本。

建议：增加定时任务，并将动态 stats 与兑换码从长期首页文案及本地化缓存键中进一步解耦；模板运行时直接读取动态字段，LLM 只生成长期文案和稳定标签。

### 8. 统一审计 Schema 与运行时 Schema 有两套表示

`schemas/game-homepage-package.schema.json` 是早期统一审计包概念；真正运行时 Schema 在 `src/gamewiki_automation/schemas.py`。

影响：新接手者可能误用概念 Schema 验证单独的首页 JSON。

建议：后续从 Python Schema 自动导出版本化 JSON Schema，或删除概念 Schema，只保留一个事实来源。

### 9. 模板契约存在跨仓库漂移风险

当前 `TEMPLATE_SITE_IDENTITY_SCHEMA` 与 `TEMPLATE_SITE_CONTENT_SCHEMA` 根据工厂 `docs/contracts/site-input.md`、`check-intake.mjs` 和 `apply-content.mjs` 实现；最终包还会强校验一张 Hero 与 favicon 7 文件。Basic Info 与模板位于同一仓库，跨契约修改必须在一个提交中同步测试。

建议：模板仓库提供版本化 JSON Schema；本项目直接读取或固定依赖该 Schema，并在 CI 中运行跨仓库契约测试。

## 当前样本特定 warning

### Anime Expeditions

- 兑换码只有第三方佐证，因此保持 `claimed-active`，首页以 `Community-reported active` 明确披露后展示。
- 上线前应人工检查官方 Discord 或官方公告。

### PursuitCore

- 当前 Place 为 `121903154323395`。
- 创建者 Linktree 仍指向旧 Place `84498985865861`；程序已记录为 rejected candidate，不能混用两者数据。
