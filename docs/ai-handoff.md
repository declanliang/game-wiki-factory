# AI 接手与标准 Prompt

## 最小背景

这是一个混合确定性代码和 LLM 判断的 Roblox 攻略站工厂。AI 的职责不是手工逐步复制文件，而是运行统一入口、读取 manifest/log、修复通用问题并续跑。

## 标准执行 Prompt

```text
请在 C:\Users\liang\Documents\Games\game-wiki-factory 中，
为 Roblox 游戏“GAME NAME”创建或续跑游戏 Wiki。

执行：python gamewiki.py "GAME NAME"
目标目录：C:\Users\liang\Documents\Games\<game-slug>

约束：
- 先读工厂 README.md、AGENTS.md、docs/architecture.md、docs/runbook.md。
- 默认复用 checkpoint；不要主动使用 refresh/recluster/overwrite。
- 失败先读目标 `.gamewiki/manifest.json` 和最新日志。
- 优先修复工厂中的通用代码，再用同一命令续跑。
- 不打印或提交任何 .env/API key。
- 不接纳完全无关关键词，不为凑数量降低门槛。
- 不手工补标签掩盖被截断的翻译。

完成标准：只保留有证据的 published 分类，通常争取 3–5 个可靠主题但不凑数；en/es/de/fr/ja/ko；六语言文章树一致；
intake、MDX、TypeScript、production build、sitemap 直接 200、self-canonical、OG 和 hreflang 全部通过。

最终报告：网站根目录、分类、语言、文章数、manifest、最新日志、API 是否复用、部署前待配置项。
```

## 只做诊断的 Prompt

```text
请诊断 C:\Users\liang\Documents\Games\<game-slug> 最近一次 Game Wiki Factory 失败。
只读取 `.gamewiki/manifest.json` 和最新日志，说明第一个失败 stage、根因、是否需要 API 重做。
不要修改代码，不要使用 refresh/overwrite。
```

## 模板升级 Prompt

```text
请使用 C:\Users\liang\Documents\Games\game-wiki-factory 的最新模板升级
C:\Users\liang\Documents\Games\<game-slug>，保留 intake 和 `.gamewiki` checkpoint，
然后执行零成本续跑与完整 production 验收。
```

## 接手检查清单

1. 确认操作的是工厂源码还是某个游戏仓库。
2. 确认游戏根目录含 `package.json`、`intake/`、`.gamewiki/manifest.json`。
3. 读取 manifest 中 `currentAttempt.log`，不要猜测失败位置。
4. 统计已存在的英文和翻译文件，避免重复 API。
5. 修改跨模块契约时同步更新 schema、模板和测试。
6. 完成后报告验证证据，不只说“代码已改”。
