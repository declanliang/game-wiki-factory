# 文档目录

根目录 [README](../README.md) 是使用入口。本目录按文档用途分类。

## 当前必须阅读

1. [已知问题](KNOWN_ISSUES.md)：项目当前仍有哪些风险和未完成项。
2. [输出规范与任务拆分](design/首页数据采集自动化-输出规范与任务拆分.md)：事实层、证据层、首页和模块规则。
3. [验收报告](testing/验收报告.md)：两个真实样本的最终结果。
4. [模板首页契约兼容性](testing/模板首页契约兼容性.md)：与 `game-wiki-template` 强制输入格式的字段映射和真实导入测试。

## 分类

### `source/`

原始需求和人工工作流，不代表当前代码的最终规则。

- [第四课原始课程文档](source/第四课、游戏首页、文章页建站数据准备%20副本.md)

### `design/`

当前数据结构、任务拆分和设计决策。

- [首页数据采集自动化：输出规范与任务拆分](design/首页数据采集自动化-输出规范与任务拆分.md)
- [语言市场调研与 LANGUAGES 决策](design/语言市场调研与-LANGUAGES-决策.md)

### `research/`

ToAPIs、OpenRouter（已淘汰）、Perplexity、Tavily（已淘汰）、Roblox 和 Jina 的历史调研。用于解释为何形成当前方案，不是运行说明。

- [游戏基础配置自动化：调研与方案](research/游戏基础配置自动化-调研与方案.md)
- [ToAPIs Responses 迁移验证](research/ToAPIs-Responses迁移验证.md)

### `prompts/`

模型任务边界和禁止项。运行时 Prompt 代码位于 `src/gamewiki_automation/prompts.py`。

- [Task 0–4 Prompt 契约](prompts/Task-0至4-Prompt契约.md)

### `examples/`

人工或其他系统生成的基准样本，仅用于对比，不是程序最终输出。

- [Anime Expeditions ChatGPT 网页版基准](examples/Anime%20Expeditions%20GPT%20产出示例.md)

### `testing/`

真实 API 样本验收、费用和缓存结果。

- [验收报告](testing/验收报告.md)
- [模板首页契约兼容性报告](testing/模板首页契约兼容性.md)
- [Anime Paradox X 语言市场验收](testing/Anime-Paradox-X-语言市场验收.md)

## 真正的运行时规范在哪里

- 模型输出 Schema：`src/gamewiki_automation/schemas.py`
- Prompt：`src/gamewiki_automation/prompts.py`
- 业务校验：`src/gamewiki_automation/validate.py`
- 完整编排：`src/gamewiki_automation/pipeline.py`
- 模板输出转换与强校验：`src/gamewiki_automation/template_contract.py`

如果历史文档与代码冲突，以运行时代码、测试和最新验收报告为准，并补充文档说明冲突原因。
