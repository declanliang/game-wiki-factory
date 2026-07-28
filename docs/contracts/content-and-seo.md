# 内容与 SEO 发布契约

目标不是机械凑页数，而是让每个公开 URL 回答一个真实玩家问题。有限的游戏身份、前置条件或相邻机制重复可以接受；页面的直接答案、决策支持、示例和主 H2 顺序必须保持独立。

## 内容边界

- 只发布有官方/创作者证据，或至少两个不同支持来源的主题。
- Codes、Tier List、Updates 和实体资料页可使用专门形态；不生成 Calculator、Planner 或 Team Builder。
- 不得用手柄支持推断 Steam Deck Verified/Playable。
- 不得把推测当事实，也不得用“可能、预计、类似游戏通常……”填充证据空白。
- 已发布的游戏或功能不得继续写成未来时态。
- 官方 YouTube 只接受频道 URL；视频 URL 只能作为视频证据。

## 元数据与链接

- 英文/拉丁语言 title 不超过 60 字符，description 不超过 160；日文建议分别不超过 36/90。
- metadata 必须在生成阶段成为完整短语；渲染层不再静默截断。
- 首页任务卡优先解析到最匹配的具体文章；无法高置信匹配时才保留分类页。
- Related 模块只展示同一分类的相关页面，不为凑数跨分类补齐。
- 图片只来自官方平台/创作者素材。重复素材在同一卡片列表中只展示一次；没有真实 alt 语义时使用空 alt。

## 发布验收

`npm run verify:site` 必须检查全部 sitemap 页面，而不只是首页：

- 直接 200、self-canonical、title、description、OG/Twitter 和完整 hreflang。
- 内部链接直接 200。
- 本站图片直接 200 且返回 image content-type。
- sitemap 页面具有站内入口，不是孤立页。
- robots 与 sitemap 全部使用同一个生产 origin。
