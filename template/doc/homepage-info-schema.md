# 站点身份 + 首页文案格式（`intake/site-identity.json` + `intake/site-content.json`）

这份文档定义 `npm run launch:site` 读取的两份**结构化**输入的完整格式规范，取代原来"自由格式调研笔记，靠 AI 读完再改写"的方式。核心原则：**这两份文件里的每个字段值，就是最终会出现在网站上的文字**——脚本只做字段搬运，不做任何二次创作/润色/翻译。字段名拼写/大小写必须跟本文档完全一致——`site-content.json` 完全不做字段名校验，写错的 key 会被脚本静默忽略（不报错、也不提醒），肉眼从生成结果上很难第一时间看出是哪个字段的问题；`site-identity.json` 稍好一点，`check:intake` 会对认不出的 key 打印一条警告（但不会阻断流程），仍然建议按文档精确核对，不要依赖这条警告兜底。

`site-content.json` 放在 `intake/` 根目录，跟 `site-identity.json` 平级，不需要单独建子目录。参考资料（`.md`/截图/旧调研笔记等）不需要放进 `intake/` 的任何位置——这些文件从不会被脚本读取，只有最终产出的 `site-content.json` 才算数，放哪都行，甚至直接贴进跟 AI 的对话里也可以。

`intake/homepage-info/site-content.json`（嵌套一层子目录）这条路径仍然被 `apply:content` 自动识别——纯粹是为了不破坏已经用这种结构上线的老项目，**新项目不要再用这个子目录**，统一用上面的扁平路径。

---

## 通用规则（两份文件都适用）

1. **JSON key 大小写必须跟本文档完全一致，一个字母都不能错**——写错的 key（大小写不对、拼错、多余空格）不会让流程失败，只会让对应的目标字段保持模板占位符/默认值不变。`site-content.json` 里这是完全静默的（`apply-content.mjs` 不校验字段名，写错的 key 原样合并进 `en.json` 变成一个没人读取的死字段，正确的字段则保持占位符）；`site-identity.json` 里 `check:intake` 会对认不出的顶层 key 打印一条警告（提示"未识别的字段"），但仍然不会阻断流程、不会告诉你"是不是想写成 XXX"，所以两份文件都要按文档精确核对大小写，不要依赖脚本兜底发现拼写错误。
2. **值一律是 JSON 字符串/数组/对象，不要用 `null`**——找不到的可选字段，要么整个不写这个 key，要么给空字符串 `""`（数组类字段给 `[]`），两种写法效果一样；不要写 `null`，也不要写"未找到"/"N/A"/"暂无"这类说明性文字（`site-identity.json` 里的链接字段会因此被脚本直接判定为无效值丢弃，见下）。
3. **不确定的事实不能编造**——`site`、`aboutGame.stats` 这类事实性字段，查不到就留空，不能为了"填满"而编一个听起来合理的值。
4. **合法 JSON**——不能有尾逗号、注释、单引号；保存前用任意 JSON 校验器/`JSON.parse` 确认能解析。

---

## 文件一：`intake/site-identity.json`（可选，但推荐——不需要 `new-site.env` 也能跑）

游戏名、官方链接这类身份字段的**标准来源**，放这里就够了，`new-site.env` 不需要创建。`GAME_NAME`/`OFFICIAL_GAME_URL`/`DISCORD_URL`/`YOUTUBE_CHANNEL_URL`/`FANDOM_URL`/`YOUTUBE_VIDEO_ID`/`LANGUAGES` 这 7 个字段每个脚本（`check:intake`/`apply:content`/`process:assets`）运行时都会直接读取这个文件（不需要先"写进 new-site.env"这一步，那是旧设计——现在是纯读取，不产生任何中间文件）。`new-site.env` 仍然可以创建，但只在没有 `intake/site-identity.json`、或者字段不在 JSON 里的情况下才会被用到——**两者都有值时，`intake/site-identity.json` 优先**（它是更新鲜、专门产出的来源）。素材路径（`HERO_IMAGE_SOURCE`/`FAVICON_SET_DIR`/`LOGO_SOURCE`/`ARTICLES_DIR`/`HOMEPAGE_INFO_DIR`）不受这条规则影响——那些同样不需要 `new-site.env`，直接按约定路径放（`intake/hero/`、`intake/favicon/` 等），见 [README.md「素材」一节](../README.md#素材)。

顶层只允许这 7 个 key：

| JSON key（区分大小写，全大写+下划线） | 必填 | 类型 | 含义 | 格式要求 |
|---|---|---|---|---|
| `GAME_NAME` | **✅ 必填** | string | 游戏官方全名 | 任意大小写都可以——如果整串全是小写，脚本会自动转成每个单词首字母大写（Title Case）；已经有自定义大小写（全大写缩写、风格化拼写如 `"inFAMOUS"`）会原样保留，不会被强制改写 |
| `OFFICIAL_GAME_URL` | **✅ 必填** | string | 官方游戏页面地址（Roblox/Steam 等） | 必须是 `http://` 或 `https://` 开头的完整 URL |
| `DISCORD_URL` | 可选 | string | 官方 Discord 邀请链接 | 必须是 `http://`/`https://` 开头的 URL，或空字符串 `""` |
| `YOUTUBE_CHANNEL_URL` | 可选 | string | 官方 YouTube 频道地址 | 同上 |
| `FANDOM_URL` | 可选 | string | 第三方 Fandom/社区 wiki 链接 | 同上 |
| `YOUTUBE_VIDEO_ID` | 可选 | string | 预告片/介绍视频 | 纯 11 位 YouTube 视频 ID，或完整链接（`youtube.com/watch?v=...`、`youtu.be/...`、`youtube.com/embed/...`、`youtube.com/shorts/...` 均可），脚本会自动提取成纯 ID；两种格式都不是的话 `check:intake` 会直接报错，需要人工修 |
| `LANGUAGES` | 可选，但建议填——见下 | string[]（小写 ISO 639-1 语言代码，如 `"en"`/`"es"`） | 这次上线打算交付哪些语言 | 每个元素必须跟 `intake/articles/` 下实际的语言子目录名完全一致（如声明了 `"es"`，就必须有 `intake/articles/es/`）。这个字段**不驱动任何脚本的实际行为**——实际处理哪些语言永远由 `intake/articles/<locale>/` 目录本身决定；它唯一的作用是让 `check:intake` 核对"声明要交付的语言"和"实际交付的语言目录"是否一致，对不上就报 error（缺语言）或 warning（多了没声明的语言），把"内容没给齐"和"模板没识别到"这两种情况分清楚 |

**关于"找不到"的字段**：`OFFICIAL_GAME_URL`/`DISCORD_URL`/`YOUTUBE_CHANNEL_URL`/`FANDOM_URL` 这 4 个字段，`check:intake` 会校验值是不是真的 `http(s)` 链接——**不是的话（包括"未找到"/"N/A"这类说明文字）会被直接当成"没有这个链接"丢弃，并打印一条警告**。所以找不到就填空字符串 `""` 或者不写这个 key，不要写文字说明，写了也不会生效，只是多一条警告。

工厂在 Basic Info 没有提供视频时，可从 Guide Search 已缓存结果中补一个严格同游戏的长视频。第三方视频只填 `YOUTUBE_VIDEO_ID`；`YOUTUBE_CHANNEL_URL` 仍只允许官方频道，不能因为嵌入了某位创作者的视频就把其频道标为官方。选择依据保存在 `.gamewiki/planning/featured-video.json`。

**示例：**
```json
{
  "GAME_NAME": "Anime-Expeditions",
  "OFFICIAL_GAME_URL": "https://www.roblox.com/games/84515722934860/Anime-Expeditions",
  "DISCORD_URL": "https://discord.gg/xxxxxxx",
  "YOUTUBE_CHANNEL_URL": "https://www.youtube.com/@xxxxxxx",
  "FANDOM_URL": "",
  "YOUTUBE_VIDEO_ID": "https://www.youtube.com/watch?v=xxxxxxxxxxx",
  "LANGUAGES": ["en", "es"]
}
```

---

## 文件二：`intake/site-content.json`（可选，但强烈建议提供）

顶层只有 `site`、`home` 两个 key，都是可选对象（整个不给就跳过，对应文案保留模板占位符，`verify:site` 会扫出来提醒你）。

### `site.*`（全部可选，事实性信息，不能编造）

| key（大小写敏感，camelCase） | 必填 | 类型 | 含义 | 格式要求 |
|---|---|---|---|---|
| `tagline` | 可选 | string | 站点副标题/小标签 | 例如 `"Fan-Made Community Wiki"` |
| `description` | 强烈建议 | string | 站点级 SEO 描述 | 约 150 字符，纯文本，不要 Markdown；不填的话首页/分享卡片的描述会保留占位符 |
| `legalNotice` | 可选 | string | 免责声明短句 | — |
| `genre` | 可选 | string[]（字符串数组） | 游戏类型标签 | 例如 `["Horror", "Simulation"]`，每个元素是英文短语 |
| `gamePlatform` | 可选 | string[] | 发行平台 | 例如 `["Roblox"]` |
| `datePublished` | 可选 | string | 发布日期 | `YYYY-MM-DD` 格式，例如 `"2024-03-01"` |
| `price` | 可选 | string | 价格 | 例如 `"Free"` |
| `priceCurrency` | 可选 | string | 货币代码 | 建议 ISO 4217 三位大写代码（如 `"USD"`），免费/不适用就填 `""`——脚本不校验这个值，纯粹透传进结构化数据 |
| `developer` | 可选 | string | 开发商名称 | — |

### `home.meta`

| key | 必填 | 类型 | 含义 |
|---|---|---|---|
| `title` | 建议填 | string | 首页专用 SEO 标题（跟 `site.description` 是两码事） |
| `description` | 建议填 | string | 首页专用 SEO 描述 |

### `home.hero`

| key | 必填 | 类型 | 含义 | 格式要求 |
|---|---|---|---|---|
| `eyebrow` | 可选 | string | 主标题上方的小标签 | 例如 `"Fan-Made Guide"` |
| `description` | 建议填 | string | 一两句话介绍核心玩法循环 | 纯文本 |
| `stats` | 可选 | `{ "value": string, "label": string }[]` | 首屏统计数字卡片 | 数组每项两个 key 必须是小写 `value`/`label`（不是 `Value`/`Label` 或 `val`/`text`），写错不会报错但也不会显示数字；最多渲染前 4 条，多写的会被截断，不需要严格限制到 4 条但没意义 |

⚠️ **不要在这里写 `title`/`secondaryCtaHref`/`videoId`**——这三个由 `site-identity.json` 的 `GAME_NAME`/`OFFICIAL_GAME_URL`/`YOUTUBE_VIDEO_ID` 自动生成；脚本按"先填自动值、再用这份文件覆盖"的顺序执行，如果这里写了这三个字段，会把正确的自动生成值覆盖掉。

### `home.aboutGame`

| key | 必填 | 类型 | 含义 | 格式要求 |
|---|---|---|---|---|
| `title` | 可选（不给自动生成 `"What is <GAME_NAME>?"`） | string | 板块标题 | — |
| `paragraphs` | 建议填 | string[] | 游戏介绍段落 | 数组每项是一段；支持 `**文字**` 语法高亮关键词（游戏名/开发商等），不支持其他 Markdown |
| `stats` | 可选 | `{ "label": string, "value": string }[]` | 右侧 Quick Facts 卡片 | 两个 key 必须是小写 `label`/`value`；内容跟 `hero.stats` 错开，不要填重复的数字 |

### `home.liveTools`（整个 key 可选——没有兑换码/排行榜这类时效性内容，就完全不要写这个 key，不要写成 `{}` 或 `{"items": []}`）

| key | 必填（写了 liveTools 就都必填） | 类型 | 含义 |
|---|---|---|---|
| `title` | 必填 | string | 板块标题 |
| `items` | 必填 | array | 见下 |

`items[]` 每一项：

| key | 必填 | 类型 | 含义 |
|---|---|---|---|
| `title` | 必填 | string | 卡片标题 |
| `description` | 必填 | string | 一行描述 |
| `href` | 必填 | string | 站内路径，如 `"/codes"`（指向具体文章/工具页，不要指向分类页） |
| `category` | 可选 | string | 匹配 `NAVIGATION_CONFIG` 的 key 就自动带对应图标，不匹配用默认图标 |

### `home.guideSections`（整个 key 可选——Basic Info 深度区）

用于把核心玩法、入门路径、成长、模式和关键系统直接解释在首页。工厂自动产出 2–4 个 section，每个 2–6 条 item；允许的 `id` 为 `core-gameplay`、`beginner-path`、`progression`、`game-modes`、`key-systems`、`current-highlights`。人类可读字段会翻译，`id/category/href` 在各语言必须完全相同。

`category` 只是 Basic Info 的分类提示，不能自行构造文章 slug。工厂在 site plan 和文章 QA 完成后，仅为 published 分类补 `href: "/<category>"`；未发布的 category/href 会被删除，因此不会产生死链。

### `home.extraSections`（整个 key 可选——数组，可以放 0 个、1 个或多个"分类精选区"）

首页除了固定的 Hero/About/Featured/FAQ 等区块之外，唯一的开放扩展点。用途：把某个内容分类里**真实、具体的条目**（角色名、职业名、道具名……而不是"共 30 篇攻略"这种统计数字）直接摆到首页，一眼就能看到核心信息，同时提升首页的游戏相关关键词密度——这是为了替代旧版模板"8 模块"机制、覆盖同一个需求（"分门别类列出信息，提升关键词密度"）而设计的，但格式不同，不能沿用旧格式。

不是所有分类都需要一个 `extraSections` 块——只给内容量足够、值得首页单独展示的分类做一块（例如角色、职业、道具、异常这类条目式内容），像"guide"这种攻略型分类已经有 `featured`/`categories`/`updates` 三个区块覆盖，不需要重复。**没有想额外展示的分类，这个字段整个不写，首页不会因此出现空白或空标题。**

顶层是一个**数组**，不是对象；数组每一项是一个区块：

| key | 必填 | 类型 | 含义 | 格式要求 |
|---|---|---|---|---|
| `title` | 必填 | string | 板块标题 | 例如 `"<Game Name> Characters"`——建议带游戏名，这正是提升关键词密度的地方 |
| `description` | 可选但建议填 | string | 标题下方一两句话的介绍 | 纯文本，同样建议自然带上游戏名/分类相关关键词，不要堆砌关键词到不像人话 |
| `viewAllHref` | 可选 | string | "查看全部"链接，指向分类页 | 例如 `"/characters"` |
| `viewAllLabel` | 可选 | string | "查看全部"按钮文字 | 例如 `"View All Characters"` |
| `items` | 必填 | array | 见下 | 建议 4-8 条，太少（1-2 条）不值得单独开一个区块，太多（10+）建议改成只放最重要的几条 + `viewAllHref` 引导去分类页 |

`items[]` 每一项（跟 `home.liveTools.items[]` 结构完全一样）：

| key | 必填 | 类型 | 含义 |
|---|---|---|---|
| `title` | 必填 | string | 条目名称，例如具体角色名/职业名/道具名 |
| `description` | 必填 | string | 一行描述 |
| `href` | 必填 | string | 站内路径，指向这个条目对应的具体文章页（不是分类页） |
| `category` | 可选 | string | 匹配 `NAVIGATION_CONFIG` 的 key 就自动带对应图标，不匹配用默认图标 |

**只有已经接入 `content/` 的真实文章能被引用**——`items[].href` 必须指向确实存在的文章页，`check:config` 会扫描所有 `xxxHref`/`href` 字段校验死链，指向不存在的文章会直接报 error。如果这一步文章还没接入（准备阶段就想先把文案写好），可以先把 `extraSections` 整个字段留到 Part 3 文章接入之后再提供，不用为了赶顺序编一个占位 href。

**示例**（假设游戏有角色和职业两类值得单独展示的内容）：

```json
"extraSections": [
  {
    "title": "<Game Name> Characters",
    "description": "Browse all playable characters in <Game Name>, including their skills and how to unlock them.",
    "viewAllHref": "/characters",
    "viewAllLabel": "View All Characters",
    "items": [
      { "title": "Character A", "description": "Starter character, strong early-game AoE damage.", "href": "/characters/character-a", "category": "characters" },
      { "title": "Character B", "description": "Support unit, unlocked after Chapter 2.", "href": "/characters/character-b", "category": "characters" }
    ]
  },
  {
    "title": "<Game Name> Classes",
    "viewAllHref": "/classes",
    "viewAllLabel": "View All Classes",
    "items": [
      { "title": "Class A", "description": "Melee-focused, high survivability.", "href": "/classes/class-a", "category": "classes" }
    ]
  }
]
```

### `home.faq`

| key | 必填 | 类型 | 含义 | 格式要求 |
|---|---|---|---|---|
| `title` | 可选（默认值 `"Frequently Asked Questions"`） | string | — | — |
| `description` | 可选（自动生成一句带游戏名的话） | string | — | — |
| `items` | 建议填 | `{ "question": string, "answer": string }[]` | 问答对 | 两个 key 必须是小写 `question`/`answer`；`question` 建议带游戏名；`answer` 支持一种链接语法 `[链接文字](/分类/slug)`，不支持其他 Markdown |

### `home.finalCta`

| key | 必填 | 类型 | 含义 |
|---|---|---|---|
| `title` | 可选（不给自动生成 `"Ready to Play <GAME_NAME>?"`） | string | — |
| `description` | 建议填 | string | 结尾行动号召文案 |

### 硬性禁止出现的字段

以下字段由 `site-identity.json`/其他脚本自动生成，**写在 `site-content.json` 里会被忽略、或者更糟——覆盖掉自动生成的正确值**：

| 字段 | 真正的来源 |
|---|---|
| `home.hero.title` / `home.hero.secondaryCtaHref` / `home.hero.videoId` | `site-identity.json` 的 `GAME_NAME`/`OFFICIAL_GAME_URL`/`YOUTUBE_VIDEO_ID` |
| `home.featured`（整个 key） | `npm run generate:featured`，按已接入的文章自动选，写文章之前这一步都不应该出现 |
| `home.categories`（整个 key） | 完全自动生成，零配置 |
| `home.updates`（整个 key） | 固定默认值，不需要配置 |

以及旧版模板（same.new 时代）遗留的字段名，当前模板完全不识别，即使输出了也没有任何效果：`modules`、`displayType`、`home.explore.modules`、`themeColor`、`sidebarCodes`、`tertiaryCta`、`home.start`。

### 完整示例

见 [`doc/examples/site-content.example.json`](examples/site-content.example.json)——一份可以直接照抄结构、替换成真实内容的完整文件：

```json
{
  "site": {
    "tagline": "Fan-Made Community Wiki",
    "description": "A complete fan-made wiki for <Game Name> on Roblox, covering classes, codes, and walkthroughs.",
    "legalNotice": "Non-official fan wiki. Made by players, for players.",
    "genre": ["Horror", "Simulation"],
    "gamePlatform": ["Roblox"],
    "datePublished": "2024-03-01",
    "price": "Free",
    "priceCurrency": "",
    "developer": "Example Studios"
  },
  "home": {
    "meta": {
      "title": "<Game Name> Wiki — Classes, Codes & Guide",
      "description": "The complete <Game Name> fan wiki: class guides, active codes, and full walkthroughs."
    },
    "hero": {
      "eyebrow": "Fan-Made Guide",
      "description": "One or two sentences on the core gameplay loop.",
      "stats": [
        { "value": "Jul 2026", "label": "Updated" },
        { "value": "1M+", "label": "Visits" }
      ]
    },
    "aboutGame": {
      "title": "What is <Game Name>?",
      "paragraphs": [
        "**<Game Name>** is a Roblox game where...",
        "Players do X, Y, Z..."
      ],
      "stats": [
        { "label": "Developer", "value": "Example Studios" },
        { "label": "Platform", "value": "Roblox" }
      ]
    },
    "extraSections": [
      {
        "title": "<Game Name> Characters",
        "description": "Browse all playable characters in <Game Name>, including their skills and how to unlock them.",
        "viewAllHref": "/characters",
        "viewAllLabel": "View All Characters",
        "items": [
          { "title": "Character A", "description": "Starter character, strong early-game AoE damage.", "href": "/characters/character-a", "category": "characters" }
        ]
      }
    ],
    "faq": {
      "title": "Frequently Asked Questions",
      "items": [
        { "question": "Is <Game Name> free to play?", "answer": "Yes, it's free on Roblox." }
      ]
    },
    "finalCta": {
      "title": "Ready to Play <Game Name>?",
      "description": "Jump in and start playing today."
    }
  }
}
```

---

## 文件三：`intake/site-content.<locale>.json`（多语言站点才需要，一个非英文语言一份）

`intake/site-identity.json` 的 `LANGUAGES` 声明了几种语言，就要给每个**非英文**语言提供一份这样的文件——文件名把 `<locale>` 换成小写 ISO 639-1 代码，比如西班牙语是 `intake/site-content.es.json`。

**跟 `intake/site-content.json` 是完全同一套 schema**（`site.*`/`home.*`，字段名、大小写、必填性、`home.extraSections`/`home.liveTools` 的整块可选规则，全部一样，见上面文件二的定义），唯一区别是**每个字符串值都已经是目标语言的成品译文**，不是英文。

- **不需要引入 `__GAME_NAME__` 这类占位符**——直接写这个语言里游戏名实际怎么称呼/拼写（通常就是英文原名，游戏名一般不翻译，除非官方有正式的本地化译名）。
- **`href`/`category` 这类站内路径字段不翻译**，跟英文版指向完全相同的路径（比如 `home.featured.items[].href` 两个语言版本应该是同一个 `"/guide/xxx"`）——路径不因为语言变化。
- 这份文件由产出 `intake/` 素材的同一个上游流程负责（跟决定 `LANGUAGES`、让 seoscout 按语言产出文章的是同一个来源）——**这个模板本身不会替你翻译这份文件**，`npm run apply:locales` 只做机械合并，缺了对应语言的文件会直接报错，找上游来源补齐。

模板自带的通用界面文案（`nav.*`/`shared.*`/`footer.*`，如"菜单""目录""隐私政策"这类每个游戏都一样的措辞）不需要放在这份文件里——那部分由模板自己维护一份跨项目复用的翻译 baseline（见 [README.md「多语言」一节](../README.md#多语言)），不是每个游戏单独产出的内容。

---

## 直接喂给内容采集 Agent 的完整 Prompt

如果「站点配置 + 首页配置」是交给一个独立的 agent 负责调研/产出，把下面这段原文直接复制给它。这段 Prompt 覆盖两份交付物，内联了必填项和字段名大小写这两条最容易出错的规则，并要求 agent 先读完整规范文档再产出、交付前自己检查一遍。

```
你的任务：为一个游戏 Wiki 站点产出两份 JSON 文件。

开始之前，先完整读一遍这份规范文档，里面是这两份文件的权威格式定义（必填项、字段类型、
大小写要求全部写在里面，本提示词下面只是摘要，规范文档优先）：
C:\Users\liang\Documents\Games\game-wiki-template\doc\homepage-info-schema.md

═══ 通用规则（两份文件都适用，最容易出错的两条）═══

1. JSON key 的大小写必须跟规范文档完全一致，一个字母都不能错——写错大小写/拼错的 key 不会让
   流程失败，只会让对应内容在最终网站上保持占位符不变（site-content.json 完全静默；
   site-identity.json 里 check:intake 会打印一条"未识别的字段"警告，但同样不会阻断流程、
   不会告诉你正确写法应该是什么，不要依赖它替你发现拼写错误）。
   site-identity.json 的 key 全大写+下划线（如 GAME_NAME）；site-content.json 的 key 是
   camelCase 小写开头（如 gamePlatform、finalCta），数组项里的 value/label/question/answer
   这类也必须是全小写。
2. 找不到的字段：可选字段留空字符串 "" 或不写这个 key；不要写"未找到"/"N/A"/"暂无"这类
   说明性文字——site-identity.json 里的链接字段会因此被直接判定无效丢弃。

═══ 第一部分：C:\Users\liang\Documents\Games\<项目目录>\intake\site-identity.json ═══

（把 <项目目录> 换成这次实际的项目文件夹名，比如 anime-expeditions）

{
  "GAME_NAME": "游戏官方全名（必填）",
  "OFFICIAL_GAME_URL": "官方游戏页面地址，必须 http(s) 开头（必填）",
  "DISCORD_URL": "官方 Discord 邀请链接，必须 http(s) 开头或留空（可选）",
  "YOUTUBE_CHANNEL_URL": "官方 YouTube 频道地址，必须 http(s) 开头或留空（可选）",
  "FANDOM_URL": "第三方 Fandom/社区 wiki 链接，必须 http(s) 开头或留空（可选）",
  "YOUTUBE_VIDEO_ID": "预告片完整链接或纯 ID，不用自己截取（可选）",
  "LANGUAGES": ["这次实际交付几种语言，就填几个小写 ISO 639-1 代码，例如 en、es（没有明确被告知要多语言，只填 [\"en\"]）"]
}

═══ 第二部分：C:\Users\liang\Documents\Games\<项目目录>\intake\site-content.json ═══

顶层 "site"（tagline/description/legalNotice/genre/gamePlatform/datePublished/price/
priceCurrency/developer，全部可选但 description 强烈建议填）和 "home"
（meta/hero/aboutGame/liveTools/extraSections/faq/finalCta）。完整字段表、每个字段的必填性、
类型、大小写要求见上面那份规范文档，直接照抄文档里"完整示例"的结构，只替换成这个游戏的真实内容。

关于 "home.extraSections"（如果你同时也在产出这次要接入的文章列表，重点看这条）：
这是首页上"分门别类展示具体条目、提升关键词密度"的区块——如果这次交付的文章里，有分类
拥有多篇值得在首页直接点名的具体条目（角色/职业/道具/异常这类条目式内容，不是攻略型内容），
可以为每个这样的分类产出一个 extraSections 数组项，"items[].href" 必须精确对应你同一批
交付的文章路径（"/<分类slug>/<文件名去掉.mdx>"，跟文章实际存放路径一致，不能是编的路径）；
如果这次没有同时产出文章、只是单独产出这两份 JSON，"home.extraSections" 直接不写这个字段，
留给文章接入之后再补，不要为了填这个字段编不存在的 href。

关于 "LANGUAGES"：这里声明的语言代码，必须跟你实际交付的 intake/articles/<locale>/ 语言
子目录完全对应——如果你同时在产出这批文章，交付了哪些 <locale>/ 目录，LANGUAGES 就填哪些；
只被要求交付英文就填 ["en"]，不要因为"以后可能要多语言"就多声明本次没有实际交付的语言，
check:intake 会拿这个字段跟 intake/articles/ 下实际的目录逐一核对，声明了但没交付会被判定
为一个需要你补齐的缺口。

硬性要求：
1. 不要输出 "modules"/"displayType"/"home.explore.modules"/"themeColor"/"sidebarCodes"/
   "tertiaryCta"/"home.start"——这些是旧版模板的字段名，当前模板完全不识别，写了没有任何效果；
   "home.extraSections" 是当前模板真正支持、格式不同的替代机制，不要把旧格式的数据套进这个字段名。
2. "site" 和 "home.aboutGame.stats" 里的都是事实性信息，不确定的字段留空或整个不写，不能编造。
3. "home.liveTools" 整个 key 可选——没有兑换码/排行榜这类时效性内容就完全不要写这个 key，
   不要写成空对象或空数组。"home.extraSections" 同样整个可选，没有值得单独展示的分类就不写。
4. 不要输出 "home.hero.title"/"home.hero.secondaryCtaHref"/"home.hero.videoId"/
   "home.featured"/"home.categories"/"home.updates"——这些由 site-identity.json 或其他
   脚本自动生成，写了会把正确的自动生成值覆盖掉。

═══ 第三部分（只有第一部分 LANGUAGES 声明了非英文语言才需要）：
C:\Users\liang\Documents\Games\<项目目录>\intake\site-content.<locale>.json ═══

LANGUAGES 里除 "en" 之外的每一种语言，都要单独产出一份，文件名把 <locale> 换成对应的小写
语言代码（比如西班牙语是 site-content.es.json）。跟第二部分完全同一套 JSON 结构、同一套
硬性要求，唯一区别：

1. 每个字符串值都写成目标语言的成品译文，不是英文——这不是把第二部分的英文值机械翻译一遍，
   而是直接用目标语言重新表达同样的信息，读起来要像母语者写的，不要有翻译腔。
2. "href"/"category" 这类站内路径字段不翻译，必须跟第二部分对应字段完全相同的值
   （游戏文章路径不因为语言变化）。
3. 游戏名本身一般不翻译，除非官方有正式的本地化译名。
4. 不需要引入任何占位符token——直接写实际内容。

这个模板本身不会翻译这份文件，只做机械合并——每种 LANGUAGES 声明的语言都必须有对应文件，
缺了 check:intake / apply:locales 会直接报错。

═══ 交付前自检清单（逐条自查，不满足就返工，不要交付一份自己都没检查过的结果）═══

1. 两份都能被标准 JSON 解析器解析，没有语法错误（尾逗号、注释、单引号都会导致解析失败）。
2. 逐个 key 对照规范文档核对大小写完全一致——这是最容易犯且最难自己发现的错误。
3. site-identity.json 里，除 GAME_NAME 外的字段要么是真实 http(s) 链接，要么是空字符串
   ""——没有写"未找到"/"N/A"/"暂无"这类说明性文字。
4. site-content.json 没有出现"硬性要求 1"和"硬性要求 4"里列出的任何字段。
5. "site.*" 和 "aboutGame.stats" 里的每一条事实都能追溯到你查到的信息来源——不确定的
   直接删掉这个字段，不要留一个"看起来合理"但是编的值。
6. "hero.stats" 不超过 4 条；"aboutGame.stats" 不要跟 "hero.stats" 填重复的数字。
7. "faq.items" 每条 answer 控制在 1-3 句话，不是大段落。
8. "extraSections" 每一项 4-8 条 items，少于 3 条就别单独开一个区块；每一项的 "href" 都能
   在你同一批交付的文章文件里找到对应的 "<分类>/<文件名>.mdx"，不是编的路径。
9. "LANGUAGES" 里的每个代码，都能在你交付的 intake/articles/ 下找到同名的语言子目录——
   声明了但没交付，或者交付了但没声明，两种情况 check:intake 都会报出来。
10. LANGUAGES 里每个非英文语言，都有对应的第三部分 site-content.<locale>.json，字段结构
    跟第二部分完全一致（同样的 key，没有多字段也没有少字段），href/category 字段的值
    逐条跟第二部分核对是否完全相同（不应该因为翻译而改变路径）。
11. 除非明确要求其他语言，第一部分和第二部分的内容用英文；第三部分反过来，必须是目标语言，
    不能偷懒直接抄第二部分的英文值。

交付格式：依次输出第一部分 site-identity.json、第二部分 site-content.json、
（如果有）第三部分每种语言各一个 site-content.<locale>.json 的完整 JSON 代码块——
每段各自独立、可以直接复制保存成对应文件，不要合并成一个 JSON、不要在代码块之间插入
除文件名以外的说明性文字。
```

## 这份格式解决的问题

以前 `HOMEPAGE_INFO_DIR` 接受自由格式调研笔记（Markdown 夹 JSON、人类批注、甚至混进旧模板字段名），需要 AI 通读理解再按 `home.*` 的目标结构重新组织、改写成营销文案——这一步本质是生成式写作，没法用脚本替代。这份结构化格式把"写文案"这件事挪到准备这两份 JSON 的阶段（不管是人工写还是用另一个 agent 产出，只要最终交付的是这个格式），`npm run apply:content` 这一步就变成纯粹的字段搬运，不需要任何理解/判断，可以完全脚本化、纳入 `npm run launch:site` 一条命令跑完的流程。
