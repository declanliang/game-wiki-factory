# Anime Paradox X 语言市场验收

检查日期：2026-07-18

## 商业策略

- 目标：为后续 SEO 文章选择更有广告变现价值的语言范围。
- 固定兜底：`en`、`es`。
- 额外调研：`de`、`fr`、`ja`、`ko`、`it`、`nl`。
- 永不考虑中文；葡语、越南语、菲律宾语、俄语等不进入当前候选范围。
- 最多 4 种语言。额外语言需要开发者本地化，或至少两个不同 URL 且来自至少两个独立发布者/域名。

## 结果

最终 `LANGUAGES`：

```json
["en", "es"]
```

德语、法语、日语、韩语、意大利语和荷兰语均完成候选记录，但没有通过非默认语言门槛。此前葡语虽然存在多来源自然热度，已按新的广告市场范围排除，不再进入搜索或最终产物。

## API 与降级

Anime Paradox X 的最终语言调研由 Perplexity `sonar-pro` 完成；ToAPIs Responses 的长联网任务返回 HTTP 524 后，现有降级链自动接管。原始结果和 `fallbackFrom` 位于：

```text
output/anime-paradox-x/raw/language-market-research.json
```

## 验证

- Place ID：`76806550943352`
- 模板契约：`pass`
- 真实模板 `check:intake`：`LANGUAGES (en, es)` 与隔离测试的 `articles/en`、`articles/es` 完全一致，0 error / 0 warning
- Anime Paradox X 单游戏缓存回归：四个模型任务均为 `cached=true`，费用 0
- 自动化测试：23 项通过（含缺失语言文件阻断、本地化结构、路径、数字事实和防英文照抄校验）

## 双样本回归

- Anime Expeditions：Place `84515722934860`，语言 `en/es/ja`，模板 `pass`
- PursuitCore：Place `121903154323395`，语言 `en/es`，模板 `pass`，旧 Place `84498985865861` 仍在 rejectedCandidates

双样本第二轮中部分上游事实缓存发生变化，导致部分下游模型缓存键更新，因此该轮不能声称所有调用都是缓存命中或费用为 0；这不影响语言范围和模板验收。
