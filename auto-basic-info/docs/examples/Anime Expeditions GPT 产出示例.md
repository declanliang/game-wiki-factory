@网页搜索
   主题词：{Anime Expeditions }（一个roblox游戏）（ 

请按以下结构提供完整的网站开发信息：
【特别注意：1.注意不要附上我的竞对的网站（官网除外）2.禁止输出任何一个404/打不开的链接】

## 1、主题基础信息

（1）给出官方网站（禁止输出任何一个404/打不开的链接）和常用社群（如Discord、reddit等）和官方 trailer youtube链接（如果没有随便选一个爆款youtube视频）。[如果官网下载不了hero图 请给我5个直接能下载的hero横图(最好带logo)]

（2）直接适合该网站的favicon logo的英文绘画提示词，目标格式为：512*512 png。

（3）搜索给出这4组用户关心的数据和SEO元数据，严格按照以下格式返回：（注意：4组用户关心的数据一定要最贴近玩家直觉，具体内容不限制，不要死板只查找Active Codes、Daily Updates、Total Visits、Units Available这4项，Players Online、 Peak CCU、User Reviews、Release Date·····都可以。注意：1.某项数据为0就不要写，比如：禁止写Active Codes：0 2.value的值后面不要写任何括号）

  {
    "home": {
      "meta": {
        "title": "游戏名 Wiki — 核心关键词1, 核心关键词2",
        "description": "SEO description（140-160字符）"
      },
      "hero": {
        "eyebrow": "Fan-Made Community Wiki（或类似标语）",
        "title": "游戏名",
        "description": "游戏核心玩法介绍，2-3句，吸引玩家点击",
        "stats": ["发布日期（如 Launched Jun 2025）", "最近更新日期", "核心数据1（如 3 Races）", "核心数据2（如 Lv100 Cap）", "核心数据3（如 130+ Skills）"],
        "primaryCta": "Start Beginner Guide（或类似首要行动按钮）",
        "secondaryCta": "Compare Races（或类似次要行动）",
        "tertiaryCta": "Check Active Codes（或类似第三行动）",
        "videoLabel": "Official media"
      },
      "start": {
        "eyebrow": "Start Here",
        "title": "Your 游戏名 Journey",
        "cards": [
          {"number": "1", "title": "Beginner Guide（固定：新手入门）", "description": "新手入门的完整攻略介绍。"},
          {"number": "2", "title": "升级/刷资源/职业/Boss 等（根据游戏特点选择）", "description": "该游戏前2小时玩家最常搜的内容。"},
          {"number": "3", "title": "与卡片2不同类型", "description": "该游戏核心玩法的教学。"},
          {"number": "4", "title": "与卡片2/3不同类型", "description": "游戏特色机制或进阶内容。"}
        ]
      },
      "aboutGame": {
        "title": "What is 游戏名?",
        "paragraphs": [
          "游戏类型和核心玩法的2-3句介绍（如：游戏名 是一个 Roblox 上受 XX 启发的格斗 RPG...）",
          "进一步说明游戏特色的2-3句（如：无论是解锁第一个 XX、进化系统、还是...）"
        ],
        "stats": [
          {"label": "Developer", "value": "开发工作室名"},
          {"label": "Platform", "value": "Roblox / Steam / PS5 等"},
          {"label": "Genre", "value": "Fighting RPG 等"},
          {"label": "Visits", "value": "12.6M+"},
          {"label": "Favorites", "value": "243K+"},
          {"label": "核心内容数", "value": "130+ Skills 等"},
          {"label": "等级上限", "value": "100 等"}
        ],
        "cta": "Explore All Guides"
      },
      "finalCta": {
        "title": "Ready to Master 游戏名?",
        "description": "号召性文案（如：From your first steps in XX to endgame boss fights, our community wiki has you covered...）",
        "primary": "Read the Beginner Guide",
        "secondary": "Play on Roblox（或对应平台）"
      }
    },
    "footer": {
      "aboutTitle": "游戏名 Wiki",
      "about": "Wiki 的简要介绍（如：游戏名 Wiki 是一个独立的粉丝攻略站，覆盖...）",
      "description": "一句话描述游戏（如：Free XX-inspired fighting RPG on Roblox. 3 races, 130+ skills, Lv100 cap.）",
      "playGame": "Play 游戏名（或对应平台按钮文字）",
      "officialDiscord": "Official Discord",
      "officialYoutube": "Official YouTube",
      "communityTool": "社区工具名称和链接（如有，如 Skill Planner）",
      "privacyPolicy": "Privacy Policy",
      "termsOfService": "Terms of Service"
    },
    "shared": {
      "wikiNavigation": "Wiki Navigation",
      "activeCodes": "Active Codes",
      "viewAllCodes": "View all codes",
      "home": "Home",
      "readMore": "Read more"
    },
    "sidebarCodes": [
      {"code": "当前有效兑换码1（如无则填暂无）", "reward": "奖励描述"},
      {"code": "当前有效兑换码2（如无则填暂无）", "reward": "奖励描述"}
    ],
    "metadata": {
      "title": "游戏名 Wiki — 核心关键词1, 核心关键词2（≤60字符）",
      "description": "简洁描述网站提供的内容和价值（140-160字符）",
      "keywords": "游戏名, 平台, 核心关键词列表（≤100字符）"
    }
  }

  完成后自查：
- home.meta.title 字符数是否 ≤ 60？
- metadata.title 字符数是否 ≤ 60？
- metadata.description 字符数是否在 140-160 之间？
- metadata.keywords 字符数是否 ≤ 100？
- home.hero.stats 数组是否为纯字符串（不含对象）？
- home.start.cards 是否有 4 个对象？
- home.aboutGame.stats 是否有 label+value 对？
- footer.about 是否有 2-3 句介绍？
- sidebarCodes 是否有 2 条兑换码？（如果没有兑换码则填"暂无"）

## 2、网站主题色应该什么颜色？默认颜色应该选择深色还是亮色

按照这种格式给我：
/* 导航页主题色 - 亮色主题 */
 --nav-theme: 152 60% 48%;  /* green-500 (原来的 #43b176) */
 --nav-theme-light: 152 60% 58%;  /* 更浅的绿色 */
 /* 导航页主题色 - 暗色主题 */
 --nav-theme: 152 60% 48%;  /* green-500 */
 --nav-theme-light: 152 60% 58%;  /* 更浅的绿色 */

## 3、多语言

根据热度，分析应该支持哪几门语言（并搜索对应本地化主题名），按流量排优先级
先说结论，按优先级排列, 最多4门语言（必须有一个是英语，中文除外）

请以清晰的 Markdown 格式返回所有信息。

**产出数据清单 **：

|数据项|说明|
|---|---|
|官方链接|官网、Discord、Reddit、YouTube trailer|
|Favicon 提示词|用于 AI 生成 favicon 的英文绘画提示词|
|Hero 区数据|badge、title、description、keywords、4 组统计数据|
|SEO 元数据|title（≤60 字符）、description（140\-160 字符）、keywords（≤100 字符）|
|主题色|HSL 格式的亮色/暗色主题色值|
|多语言|最多 4 门语言的优先级排列（含本地化名称）|
思考了 5m 45s
1、主题基础信息

数据检索时间：2026 年 7 月 16 日。
Anime Expeditions 暂未发现独立官方网站，因此应将 Roblox 游戏页作为官网入口。官方 X 账号标注正式发布时间为 2026 年 7 月 17 日；Roblox 页面当前显示为 TIME CHAMBER 阶段。

（1）官方链接与社群
类型	链接	说明
官方游戏页	Play Anime Expeditions on Roblox	最重要的官网入口，由 Expeditions Entertainment 发布
官方 Roblox 社群	Expeditions Entertainment	开发团队 Roblox 社群
官方 Discord	Anime Expeditions Discord	公告、更新、兑换码和玩家交流
官方 YouTube	Anime Expeditions YouTube	Trailer、玩法预览和官方宣传片
官方 X / Twitter	@ExpeditionsRBLX	发布日期、更新和活动公告
官方 Trailer	Anime Expeditions Official Trailer	官方完整 Trailer
官方 Gameplay	Official Anime Expeditions Gameplay Sneak	官方玩法预览
Reddit	暂无可验证的官方 Reddit	不建议在 Footer 中添加非官方 Subreddit

官方 Roblox 页面确认了开发者、召唤单位、升级进化、Expeditions、Boss、多人合作等核心玩法；Discord 邀请和 YouTube 频道目前均可访问。

可直接下载的 Hero 横图

由于 Roblox 页面没有提供完整的官方媒体下载中心，下面使用 Roblox 官方 CDN 和官方 YouTube 视频缩略图作为可下载素材：

Roblox 官方游戏横图
官方 Trailer 缩略图
官方 Gameplay Sneak 缩略图
官方 Story Teaser 缩略图
官方 Trailer 自动截帧

其中第 1 张最接近 Roblox 官方游戏封面；第 2 至第 4 张适合作为内容页 Banner。YouTube 缩略图建议裁剪为 1600×900 或 1920×1080 后再进行 AI 放大，避免直接拉伸。

（2）Favicon Logo 英文绘画提示词
Create a clean 512x512 PNG favicon logo for a fan-made wiki about an anime-inspired Roblox tower defense game. Center a stylized compass rose fused with a glowing expedition portal, with a small golden star at the north point. Use electric cyan, luminous blue, warm orange and subtle gold highlights over a deep navy background. Bold geometric silhouette, polished fantasy game icon, crisp vector-like edges, strong contrast, symmetrical composition, minimal small details, transparent outer padding, no text, no letters, no copyrighted characters, and clearly readable at 32x32 pixels.

建议参数：

Canvas: 512x512
Format: PNG
Background: transparent or deep navy circular background
Style: polished fantasy game icon, vector-like, high contrast
Negative prompt: text, watermark, realistic face, copyrighted anime character, excessive detail, blurry edges
（3）Hero、SEO 与网站文案 JSON
{
  "home": {
    "meta": {
      "title": "Anime Expeditions Wiki — Codes, Units & Tier List",
      "description": "Master Anime Expeditions with active codes, unit tier lists, beginner guides, evolution tips, traits, expeditions, bosses, and update news for Roblox."
    },
    "hero": {
      "eyebrow": "Fan-Made Anime Tower Defense Wiki",
      "title": "Anime Expeditions",
      "description": "Build a squad of anime-inspired units, defend against enemy waves, and clear dangerous expeditions across fractured worlds. Summon, level, evolve, and optimize your team for bosses, challenges, and co-op play.",
      "stats": [
        "Full Release Jul 17, 2026",
        "Updated Jul 14, 2026",
        "99% Approval",
        "24-Player Servers",
        "3 Active Codes"
      ],
      "primaryCta": "Start Beginner Guide",
      "secondaryCta": "View Unit Tier List",
      "tertiaryCta": "Check Active Codes",
      "videoLabel": "Official media"
    },
    "start": {
      "eyebrow": "Start Here",
      "title": "Your Anime Expeditions Journey",
      "cards": [
        {
          "number": "1",
          "title": "Beginner Guide",
          "description": "Learn the opening progression route, first summons, essential menus, early currencies, and the mistakes that slow down a new account."
        },
        {
          "number": "2",
          "title": "Best Units & Reroll Priorities",
          "description": "See which early units are worth keeping, where to spend Gems, and when rerolling or saving for a stronger banner makes more sense."
        },
        {
          "number": "3",
          "title": "Traits, Leveling & Evolution",
          "description": "Understand how to strengthen units, choose useful traits, gather evolution materials, and unlock stronger abilities without wasting resources."
        },
        {
          "number": "4",
          "title": "Expeditions, Bosses & Team Building",
          "description": "Build balanced teams for wave defense, special modes, and boss encounters, including placement, upgrade order, and co-op role basics."
        }
      ]
    },
    "aboutGame": {
      "title": "What is Anime Expeditions?",
      "paragraphs": [
        "Anime Expeditions is a Roblox strategy tower defense game by Expeditions Entertainment. Players summon anime-inspired units, deploy them against waves of enemies, and progress through expeditions filled with challenges and bosses.",
        "Units can be leveled, evolved, and developed into stronger team roles. The game supports solo and cooperative play, so progression depends on smart summoning, resource management, positioning, and team synergy."
      ],
      "stats": [
        {
          "label": "Developer",
          "value": "Expeditions Entertainment"
        },
        {
          "label": "Platform",
          "value": "Roblox"
        },
        {
          "label": "Genre",
          "value": "Strategy Tower Defense"
        },
        {
          "label": "Full Release",
          "value": "Jul 17, 2026"
        },
        {
          "label": "Latest Update",
          "value": "Jul 14, 2026"
        },
        {
          "label": "Server Size",
          "value": "24"
        },
        {
          "label": "Approval",
          "value": "99%"
        }
      ],
      "cta": "Explore All Guides"
    },
    "finalCta": {
      "title": "Ready to Master Anime Expeditions?",
      "description": "From your first summon to evolved endgame squads and difficult boss runs, this fan-made wiki helps you spend resources wisely and build a stronger expedition team.",
      "primary": "Read the Beginner Guide",
      "secondary": "Play on Roblox"
    }
  },
  "footer": {
    "aboutTitle": "Anime Expeditions Wiki",
    "about": "Anime Expeditions Wiki is an independent fan-made guide site covering codes, units, traits, evolution, expeditions, bosses, and beginner progression. It is not affiliated with Roblox or Expeditions Entertainment.",
    "description": "Anime-inspired strategy tower defense on Roblox with summoning, evolution, expeditions, bosses, and co-op play.",
    "playGame": "Play Anime Expeditions",
    "officialDiscord": "Official Discord",
    "officialYoutube": "Official YouTube",
    "communityTool": "Official X Updates",
    "privacyPolicy": "Privacy Policy",
    "termsOfService": "Terms of Service"
  },
  "shared": {
    "wikiNavigation": "Wiki Navigation",
    "activeCodes": "Active Codes",
    "viewAllCodes": "View all codes",
    "home": "Home",
    "readMore": "Read more"
  },
  "sidebarCodes": [
    {
      "code": "RELEASE",
      "reward": "30 Trait Crystals and 2,500 Gems"
    },
    {
      "code": "EA+",
      "reward": "30 Trait Crystals and 2,500 Gems"
    }
  ],
  "metadata": {
    "title": "Anime Expeditions Wiki — Codes, Units & Tier List",
    "description": "Master Anime Expeditions with active codes, unit tier lists, beginner guides, evolution tips, traits, expeditions, bosses, and update news for Roblox.",
    "keywords": "Anime Expeditions, Roblox, codes, tier list, units, traits, evolution, beginner guide"
  }
}
数据说明

Roblox 当前搜索结果显示游戏类型为 Strategy、服务器上限为 24、最近更新时间为 2026 年 7 月 14 日，并显示约 99% 的玩家认可度；这些动态数据后续可能随正式上线发生变化。

正式发布日期来自官方 X 账号；玩法描述来自官方 Roblox 页面，包括召唤、升级、进化、多种 Expeditions、Boss 和多人合作。

兑换码属于高度动态数据。RELEASE、EA+ 和 EA 是当前公开信息中出现的三条代码，但正式发布前应再次进入官方 Discord 的兑换码频道验证奖励和有效状态。官方 Discord 本身可以正常访问，但其频道内容无法通过公开网页完整读取。

字段对应链接
footer.playGame:
https://www.roblox.com/games/84515722934860/Anime-Expeditions

footer.officialDiscord:
https://discord.com/invite/animeexpeditions

footer.officialYoutube:
https://www.youtube.com/@AnimeExpeditionsOfficial

footer.communityTool:
https://x.com/ExpeditionsRBLX
JSON 自查结果
检查项	结果
home.meta.title	49 字符，≤60
home.meta.description	150 字符
metadata.title	49 字符，≤60
metadata.description	150 字符，符合 140–160
metadata.keywords	85 字符，≤100
home.hero.stats	5 条，全部为纯字符串
home.start.cards	4 个对象
home.aboutGame.stats	全部包含 label 和 value
footer.about	2 句
sidebarCodes	2 条
2、网站主题色与默认模式
结论

默认选择深色主题。

原因是官方视觉素材主要使用深蓝、宇宙黑、发光青蓝、橙金色能量特效。深色背景可以更好地承载单位卡片、稀有度标签、技能图标和发光按钮，也更符合 Anime Tower Defense 玩家对攻略站的视觉预期。

建议：

主导航色：Electric Blue
Hover 与高亮色：Luminous Cyan
次要强调色：Warm Orange / Gold
页面背景：Deep Navy
普通正文：Cool White
稀有度与活动 Badge：Orange、Purple、Gold
/* 导航页主题色 - 亮色主题 */
--nav-theme: 202 88% 48%;        /* electric blue */
--nav-theme-light: 190 90% 57%;  /* luminous cyan */

/* 导航页主题色 - 暗色主题 */
--nav-theme: 198 92% 58%;        /* brighter electric cyan-blue */
--nav-theme-light: 187 95% 68%;  /* glowing cyan */

可选辅助色：

/* 页面辅助颜色 */
--accent-warm: 28 92% 58%;       /* orange energy */
--accent-gold: 43 92% 58%;       /* legendary gold */
--page-background: 222 42% 8%;   /* deep navy */
--card-background: 220 34% 12%;  /* elevated dark card */
--card-border: 207 40% 23%;      /* blue-gray border */

推荐默认设置：

Default appearance: Dark
Primary theme: Electric blue
Secondary accent: Orange-gold
Card style: Dark translucent panels with cyan borders
3、多语言优先级
结论

按照当前游戏热度、官方 Trailer 地区表现以及已经出现的本地玩家内容，建议优先支持：

英语
巴西葡萄牙语
泰语
越南语

官方 Trailer 曾在美国、加拿大、巴西和泰国等地区进入 YouTube 趋势榜；同时已经能够检索到越南语玩家发布的 Early Access 和上线讨论。

优先级	语言	Locale	推荐本地化主题名	URL 结构	说明
1	English	en	Anime Expeditions Wiki	/ 或 /en	官方内容和游戏 UI 的核心语言
2	Português do Brasil	pt-BR	Anime Expeditions Wiki — Códigos e Tier List	/pt-br	Trailer 在巴西热度明显，Roblox 巴西用户搜索量较大
3	ไทย	th	Anime Expeditions Wiki — โค้ดและ Tier List	/th	Trailer 在泰国进入趋势榜，塔防和动漫 Roblox 游戏受众活跃
4	Tiếng Việt	vi	Anime Expeditions Wiki — Code và Bảng Xếp Hạng	/vi	已出现越南语 Early Access、Trailer 和玩家讨论内容
本地化游戏名建议

官方品牌名没有发现正式翻译版本，因此 H1、Logo、页面 Title 中应保留 Anime Expeditions，只翻译后面的 Wiki 关键词。

{
  "en": {
    "gameName": "Anime Expeditions",
    "siteName": "Anime Expeditions Wiki"
  },
  "pt-BR": {
    "gameName": "Anime Expeditions",
    "siteName": "Anime Expeditions Wiki — Códigos e Tier List",
    "localizedMeaning": "Expedições de Anime"
  },
  "th": {
    "gameName": "Anime Expeditions",
    "siteName": "Anime Expeditions Wiki — โค้ดและ Tier List",
    "localizedMeaning": "อนิเมะ เอ็กซ์เพดิชันส์"
  },
  "vi": {
    "gameName": "Anime Expeditions",
    "siteName": "Anime Expeditions Wiki — Code và Bảng Xếp Hạng",
    "localizedMeaning": "Cuộc Thám Hiểm Anime"
  }
}

不建议直接把品牌 H1 改成 Expedições de Anime、Cuộc Thám Hiểm Anime 等纯翻译名称，否则可能削弱对精确关键词 Anime Expeditions 的搜索匹配。

@网页搜索
 主题词：{Anime Expeditions}
我要做首页，准备8个小模块（除hero、除FAQ），覆盖用户常见SEO谷歌搜索（如codes、beginner guide、tier list），且资料网上可以搜索到，按重要程度排序。禁止无意义模块。

请严格按以下 JSON 结构输出，每个模块一个对象，匹配 en.json 的 home.explore.modules 格式：

{
  "modules": [
    {
      "order": 1,
      "name": "<全英文，格式：游戏名 xxx，如 Star Savior Codes>",
      "description": "<2-3 句模块介绍>",
      "href": "</模块对应内页路径，如 /codes>",
      "displayType": "<仅限 4 种：code-cards | step-by-step | tier-grid | card-list>",
      "highlights": [
        {"label": "<标签/序号/等级>", "detail": "<具体内容描述>", "badge": "<可选，如 Active/New>"}
      ],
      "references": ["<具体可访问的网站链接，禁止捏造>"]
    }
  ]
}

要求：
- modules 数组包含 8 个对象，按重要程度排序
- href 为该模块点击后的跳转路径（内部页面 slug）
- displayType 仅限 4 种：code-cards（兑换码卡片）、step-by-step（步骤指引）、tier-grid（等级网格/S/A/B/C）、card-list（普通卡片列表）
- highlights 中填充真实游戏数据，禁止捏造；结构由 displayType 决定：
  - code-cards：每条为 1 个兑换码（label=码名，detail=奖励，badge=状态如 Active/Expired）
  - step-by-step：每条为 1 个步骤（label=序号，detail=步骤内容）
  - tier-grid：每条为 1 个等级（label=S/A/B/C，detail=该等级包含的内容）
  - card-list：每条为 1 个卡片（label=图标文字，detail=卡片内容）
- references 必须有值，列出真实可访问的链接
- references 严禁包含竞对站、Wiki/Fandom/聚合 wiki 链接（如 wiki.gg、fandom、fextralife、第三方攻略 wiki）；优先使用官网、官方商店、官方社媒、官方公告、官方视频、权威媒体
- 只输出 JSON，不要包含任何 markdown 标记或解释文字

**产出数据清单 **：

|数据项|说明|
|---|---|
|模块顺序|order 1\-8，按 SEO 价值排序|
|模块名称|格式「主题名 \+ 功能词」，如 "Cursed Gear Codes"|
|模块描述|2\-3 句介绍|
|跳转路径|href，内页 slug|
|展示形式|displayType，仅 code\-cards / step\-by\-step / tier\-grid / card\-list|
|数据条目|highlights 数组，每条含 label \+ detail \+ 可选 badge|
|参考链接|真实可访问的外部链接|
思考了 3m 51s

{
"modules": [
{
"order": 1,
"name": "Anime Expeditions Codes",
"description": "Find the latest working Anime Expeditions codes for free Gems and Trait Crystals. Copy each code exactly and redeem it before launch rewards or update bonuses expire.",
"href": "/codes",
"displayType": "code-cards",
"highlights": [
{
"label": "EA+",
"detail": "2,500 Gems and 30 Trait Crystals",
"badge": "Active"
},
{
"label": "EA",
"detail": "2,500 Gems and 20 Trait Crystals",
"badge": "Active"
},
{
"label": "RELEASE",
"detail": "2,500 Gems and 30 Trait Crystals",
"badge": "Active"
}
],
"references": [
"https://beebom.com/anime-expeditions-codes/",
"https://discord.com/invite/animeexpeditions",
"https://www.roblox.com/games/84515722934860/Anime-Expeditions"
]
},
{
"order": 2,
"name": "Anime Expeditions Beginner Guide",
"description": "Follow the safest early-game route through the Beginner's Path, banners, quests, and account progression. This guide focuses on guaranteed rewards and confirmed systems instead of wasting Gems or upgrade materials.",
"href": "/beginner-guide",
"displayType": "step-by-step",
"highlights": [
{
"label": "1",
"detail": "Open the official Roblox experience and begin the Beginner's Path, which acts as the game's extended tutorial."
},
{
"label": "2",
"detail": "Complete Beginner's Path quests to claim the guaranteed Farm unit and guaranteed Mythic unit."
},
{
"label": "3",
"detail": "Unlock the exclusive Beginner Banner before spending heavily on other summon banners."
},
{
"label": "4",
"detail": "Complete Daily Quests, Weekly Quests, Unit Trials, and Achievements for additional progression rewards."
}
],
"references": [
"https://www.roblox.com/games/84515722934860/Anime-Expeditions",
"https://beebom.com/anime-expeditions-patch-notes-and-updates/",
"https://www.youtube.com/watch?v=i2mgyEhZtZc"
]
},
{
"order": 3,
"name": "Anime Expeditions Tier List",
"description": "Compare the strongest currently tested units while keeping unfinished launch units separate from confirmed rankings. Placements are provisional because balance, evolution state, equipment, traits, and game mode can change unit performance.",
"href": "/tier-list",
"displayType": "tier-grid",
"highlights": [
{
"label": "S",
"detail": "Cursed Student (True Love) is the leading public-test candidate due to scaling follow-up attacks and Bleed-based Bat Spirits."
},
{
"label": "A",
"detail": "Salmon Sorcerer (Grade 1) provides Slow and Stagger control, while The Hero supports teams built around Physical units."
},
{
"label": "B",
"detail": "Elf Mage (Unleashed), Flame Emperor (Reincarnate), Hollow (Blaze), Lady Giant (Envy), Puppet (Telekinetic), Reaper (Released), and String Demon (Awakened) still need equal-condition testing."
},
{
"label": "C",
"detail": "No reliable C-tier placement is confirmed yet; launch balance and repeatable Sandbox tests are required before marking a unit as outclassed."
}
],
"references": [
"https://www.youtube.com/watch?v=DjbxDcaIjwA",
"https://www.youtube.com/watch?v=i2mgyEhZtZc",
"https://beebom.com/anime-expeditions-patch-notes-and-updates/"
]
},
{
"order": 4,
"name": "Anime Expeditions Units",
"description": "Browse the confirmed EA+ roster and recognize each unit by its in-game alias and form name. The index can expand with rarity, abilities, obtain methods, evolution recipes, and performance data as more values are verified.",
"href": "/units",
"displayType": "card-list",
"highlights": [
{
"label": "Top Roster",
"detail": "8th Sword (Berserk), Shadow (Divine), Crimson (Brother), Toy Maker, and True Saint (Holy)"
},
{
"label": "Mythic Group",
"detail": "Cursed Student (True Love), Elf Mage (Unleashed), Flame Emperor (Reincarnate), and Hollow (Blaze)"
},
{
"label": "Utility Group",
"detail": "Lady Giant (Envy), Puppet (Telekinetic), Reaper (Released), and Salmon Sorcerer (Grade 1)"
},
{
"label": "Control Unit",
"detail": "String Demon (Awakened) is included among the 14 units introduced with the EA+ release."
}
],
"references": [
"https://beebom.com/anime-expeditions-patch-notes-and-updates/",
"https://x.com/ExpeditionsRBLX/status/2069807917545504896",
"https://www.youtube.com/@AnimeExpeditionsOfficial"
]
},
{
"order": 5,
"name": "Anime Expeditions Traits and Rerolls",
"description": "Learn how Trait Crystals support the unit reroll system and where to obtain an early supply without spending premium currency. Save limited crystals for units that remain in your main Story, Expedition, Raid, or Tournament teams.",
"href": "/traits",
"displayType": "card-list",
"highlights": [
{
"label": "Trait Crystals",
"detail": "Trait Crystals are used to reroll traits on units."
},
{
"label": "EA+ Reward",
"detail": "The EA+ code grants 30 Trait Crystals and 2,500 Gems."
},
{
"label": "EA Reward",
"detail": "The EA code grants 20 Trait Crystals and 2,500 Gems."
},
{
"label": "Release Reward",
"detail": "The RELEASE code grants 30 Trait Crystals and 2,500 Gems, bringing the three-code total to 80 Trait Crystals."
}
],
"references": [
"https://beebom.com/anime-expeditions-codes/",
"https://discord.com/invite/animeexpeditions",
"https://www.roblox.com/games/84515722934860/Anime-Expeditions"
]
},
{
"order": 6,
"name": "Anime Expeditions Expeditions Guide",
"description": "Understand the game's signature Expeditions mode, including resource gathering, base building, objectives, and Payload gameplay. Use this section to plan teams for content that differs from standard tower defense stages.",
"href": "/expeditions",
"displayType": "card-list",
"highlights": [
{
"label": "Resources",
"detail": "Expeditions is a key mode for gathering resources used throughout account and unit progression."
},
{
"label": "Base Building",
"detail": "Players build and develop their own base while participating in Expeditions."
},
{
"label": "Objectives",
"detail": "Expedition runs include objectives rather than relying only on standard wave-clearing rules."
},
{
"label": "Payload",
"detail": "The mode contains an exclusive Payload experience that changes the normal tower defense format.",
"badge": "Featured"
}
],
"references": [
"https://beebom.com/anime-expeditions-patch-notes-and-updates/",
"https://www.roblox.com/games/84515722934860/Anime-Expeditions",
"https://www.youtube.com/watch?v=ysDUclBoJHk"
]
},
{
"order": 7,
"name": "Anime Expeditions Raids Guide",
"description": "Prepare for cooperative Raid encounters featuring enemy waves and large bosses. The guide should track entry requirements, boss mechanics, team roles, rewards, and recommended units as each Raid becomes testable.",
"href": "/raids",
"displayType": "step-by-step",
"highlights": [
{
"label": "1",
"detail": "Summon, level, and evolve a balanced squad before entering difficult cooperative content."
},
{
"label": "2",
"detail": "Invite friends or form a party because the official game description confirms cooperative wave and boss battles."
},
{
"label": "3",
"detail": "Use area damage and control units to manage incoming enemy waves before the boss reaches the defense objective."
},
{
"label": "4",
"detail": "Save high-damage upgrades and team support for the towering boss encounters shown in official Raid media."
}
],
"references": [
"https://www.youtube.com/watch?v=D9PhFvTdXUE",
"https://www.roblox.com/games/84515722934860/Anime-Expeditions",
"https://www.youtube.com/@AnimeExpeditionsOfficial"
]
},
{
"order": 8,
"name": "Anime Expeditions Updates",
"description": "Track new units, modes, events, equipment, and quality-of-life improvements added in each Anime Expeditions update. The EA+ release introduced major progression systems that should be separated into searchable patch-note sections.",
"href": "/updates",
"displayType": "card-list",
"highlights": [
{
"label": "14 New Units",
"detail": "The July 15, 2026 EA+ release introduced 14 named units across Mythic and other high-rarity groups.",
"badge": "New"
},
{
"label": "Tournaments",
"detail": "Solo and Duo Tournaments were added alongside Infinite Global Leaderboards."
},
{
"label": "Season 1",
"detail": "The Crimson-themed Battle Pass includes an exclusive Crimson unit and a Crimson AoE Indicator Color."
},
{
"label": "Quality of Life",
"detail": "Auto Upgrade, Unit Manager, Right Click Unequip, Phantom Placement, and in-match inventory access were added."
}
],
"references": [
"https://beebom.com/anime-expeditions-patch-notes-and-updates/",
"https://x.com/ExpeditionsRBLX",
"https://discord.com/invite/animeexpeditions"
]
}
]
}