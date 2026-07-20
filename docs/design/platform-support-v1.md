# Roblox / Steam 平台支持设计

## 决策

Roblox 与 Steam 不复制两套工厂。二者采用“平台适配器 + 统一下游契约”：平台适配器只负责确认游戏身份、读取官方事实并映射成规范 `facts.json`；Basic Info 之后的搜索、规划、文章、翻译、intake、Next.js 模板和验收全部复用。

```text
game + platform + optional official URL
  ├─ Roblox adapter → Place / Universe / Roblox facts
  └─ Steam adapter  → App ID / Steam Store facts
                ↓
        canonical facts + evidence
                ↓
   shared Basic Info → Guide Search → SEO Scout → template
```

## 统一部分

- 输出目录、manifest、日志和 checkpoint。
- `site-identity.json`、`site-content*.json`、`game-profile.json` 与 `site-plan.json`。
- 固定语言 `en/es/de/fr/ja/ko`。
- 搜索证据、关键词筛选、文章生成、相关性 QA 和翻译。
- 首页、内链、MDX、TypeScript、production build、sitemap、canonical 与 hreflang 验收。

## 平台专属部分

|领域|Roblox|Steam|
|---|---|---|
|身份主键|Place ID / Universe ID|App ID|
|官方入口|Roblox experience page|Steam Store app page|
|核心事实|creator、visits、server size、updated|developer、release、price、reviews、features、requirements|
|媒体|Roblox thumbnail/icon|Steam header/screenshots/movies|
|搜索消歧|游戏名 + Roblox|游戏名 + Steam|

首页只展示有官方事实支持的平台指标。Steam 的完整手柄支持不能推导为 Steam Deck Verified 或 Playable；Roblox 的候选名称相似也不能覆盖 token 不一致。

## 执行约定

```powershell
python gamewiki.py "Roblox Game" --platform roblox
python gamewiki.py "Steam Game" --platform steam --official-url "https://store.steampowered.com/app/<id>/<slug>/"
```

可以省略 `--platform` 使用 `auto`，但同名、歧义或跨平台游戏应显式指定。当前仅支持 Roblox 与 Steam；新增平台必须实现官方身份与事实 adapter、复用规范契约，并增加真实端到端样本。

## Funnel Runners 验收样本

Funnel Runners（Steam App ID `3712080`）已完成真实端到端验证：Basic Info、Guide Search、5 个英文主题、五种翻译、30 篇 MDX、intake、TypeScript、production build 与本地 HTTP/SEO 验收全部通过。该样本同时验证了官方商店 URL 定位、Steam hero stats、官方 trailer 和 Steam Deck 未确认状态的保守表达。
