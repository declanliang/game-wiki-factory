# AI / 开发者执行说明

本文件用于让新的 AI 或开发者无需阅读全部历史调研即可安全接手项目。

## 项目目标

只输入 Roblox 或 Steam 游戏名，输出可供通用 Wiki 网站模板使用的首页配置、模块、来源证据和图片资产。

当前范围只包括原始课程文档的“## 一、首页数据采集”，不包括内页 SEO 文章流程。

## 首次接手顺序

1. 阅读根目录 `README.md`。
2. 阅读 `docs/KNOWN_ISSUES.md`。
3. 查看 `src/gamewiki_automation/pipeline.py` 理解编排。
4. 查看 `src/gamewiki_automation/schemas.py` 理解模型输出结构。
5. 运行测试，不要先执行付费的 `--refresh`。

```powershell
python -m pip install -e .
python -m unittest discover -s tests -v
python -m gamewiki_automation "Anime Expeditions"
```

最后一条默认应命中缓存；只有用户明确要求强制刷新时才使用 `--refresh`。

## 不能破坏的规则

- 不读取、打印、复制或提交 `.env` 中的值。
- 不把 Tavily 重新加入运行链。
- 不把 OpenRouter 重新加入运行链；主模型 API 是 ToAPIs Responses API。
- 联网必须使用支持 `web_search_preview` 的 `TOAPIS_WEB_MODEL`，默认 `gpt-5.3-codex-official`。
- 不允许 LLM 覆盖 Roblox 或 Steam 官方 API 已确认的身份和动态事实。
- Roblox 使用 Place/Universe，Steam 使用 App ID；平台字段不可混用。Steam 手柄支持不可推导为 Deck Verified/Playable。
- 不允许虚构 URL、兑换码、数值、日期、玩法或社区共识。
- 不允许将普通 HTTP 200 直接等同于“官方所有权已验证”。
- 第三方代码必须保持 `claimed-active` / `Unverified`。
- 不为满足 8 个模块而生成无资料模块。
- 不把 Fandom、wiki.gg、fextralife 或竞对 Wiki 放入前台 references。
- 修改 Schema、缓存键或 Prompt 后，必须重新运行两个产物回归测试。
- 工厂内置 `template/` 消费同级的 `site-identity.json`、`site-content.json` 与每个非英语语言的 `site-content.<locale>.json`；不得把内部 `00首页信息.json` 直接复制给模板。
- 最终 `template-intake/` 顶层只能有两个基础 JSON、LANGUAGES 要求的本地化 JSON、一张 `hero.<ext>` 和 `favicon/`；不得把内部 Hero 候选或 `source-icon.png` 混入。
- 基础与本地化模板输出必须同时通过 Schema、事实一致性、结构同构和不可翻译路径校验，禁止靠 Prompt 声称格式正确。
- `site-content.json` 顶层只能有 `site/home`；禁止 `themeColor/modules/displayType/home.start` 和 Hero 自动字段。

## 代码地图

|文件|职责|
|---|---|
|`cli.py`|命令行参数和多游戏执行|
|`config.py`|`.env` 与默认配置|
|`http.py`|重试和 HTTP 缓存|
|`roblox.py`|Discover、身份评分、Roblox 官方事实|
|`steam.py`|Steam Store 搜索、App ID 身份与 Steam 官方事实|
|`llm.py`|ToAPIs Responses、Perplexity 降级、JSON 修复与模型缓存|
|`prompts.py`|外部事实、语言市场、首页和模块 Prompt|
|`schemas.py`|研究、首页和模块运行时 Schema|
|`pipeline.py`|Task 0–6 编排和证据合并|
|`media.py`|Hero 下载、主色提取、favicon 包|
|`validate.py`|Schema 与业务规则校验|
|`report.py`|生成 `00基础信息.md`|
|`template_contract.py`|确定性生成并强校验基础及多语言模板文件|

## 正常修改后的验证

```powershell
python -m compileall -q src tests
python -m unittest discover -s tests -v
python -m gamewiki_automation "Anime Expeditions" "PursuitCore"
```

验收要求：

- 测试全部通过。
- Anime Place 为 `84515722934860`。
- PursuitCore Place 为 `121903154323395`。
- PursuitCore rejectedCandidates 包含 `84498985865861`。
- 两个 `validation-report.json` 都不能是 `fail`。
- 两个 `template-validation-report.json` 必须是 `pass`。
- `site-identity.json` 只能有规范的 7 个大写 key（含 `LANGUAGES`）；Factory 新站语言策略必须严格为 `en/es`，不在建站阶段执行单游戏语言市场调研。`de/fr/ja` 属于上线后的 Growth Agent 扩展。`site-content.json` 顶层只能有 `site/home`。
- Hero stats 不超过 4 个 `{value,label}` 对象，FAQ answer 必须为 1–3 句。
- 缓存回归时所有 LLM call 的 `cached` 应为 true，本次费用应为 0。

## 文档维护规则

- 面向普通使用者的变化写入 `README.md`。
- 当前问题写入 `docs/KNOWN_ISSUES.md`。
- 架构和字段决策优先写入 Factory 根目录 `docs/HANDOFF.md`；模块内部细节写入本模块 `docs/` 下的现有分类。
- API 历史测试写入 `docs/research/`，不要塞回 README。
- 样本和对比材料写入 `docs/examples/`。
- 验收结果写入 `docs/testing/`。
