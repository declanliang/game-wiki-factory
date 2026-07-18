# seoscout

> **从关键词到多语言文章 —— 一条命令搞定。**

seoscout 是一个面向 SEO 从业者和内容创作者的命令行工具。给它一份关键词列表，它会自动完成：

- 🔍 **搜索** —— 并行搜索 YouTube（通过 DataForSEO）和 Google（通过 Serper API）
- 📥 **收集** —— 抓取 YouTube 视频字幕和网页正文（通过 Jina Reader）
- ✍️ **生成** —— 用 LLM 生成 SEO 优化的 MDX 文章（带 JS 格式的 export metadata，自动带开头 Quick Guide 摘要框和正文高亮提示框）
- 🌍 **翻译** —— 将文章翻译成多种语言

不用再一个个手动打开搜索结果、复制粘贴,也不用花钱买昂贵的内容工具。

## 功能特性

- **完整流水线** —— 关键词 → 搜索 → 收集 → 生成 → 复核 → 翻译
- **并行搜索** —— YouTube + Google 同时进行
- **LLM 驱动写作** —— 基于收集到的素材生成 SEO 文章
- **多语言** —— 将文章翻译成任意语言（西班牙语、日语、阿拉伯语等）
- **智能过滤** —— 搜索 query 自动消歧、按时长过滤、屏蔽竞品/垃圾域名
- **文不对题复核** —— 生成后自动用 LLM 复核每篇文章是否真的在讲这个游戏，删掉跑题的，不浪费翻译成本
- **缓存机制** —— 每个来源只提取一次，重新运行会跳过已缓存内容
- **DataForSEO 驱动的 YouTube** —— 搜索和字幕都走官方 SERP API，不依赖 yt-dlp 或代理 IP，不会被封
- **可配置** —— 通过 `.env` 控制并发数、批量大小、LLM 模型等

## 快速开始

### 前置条件

- Python 3.10+
- 一个 [DataForSEO](https://app.dataforseo.com/api-dashboard) 账号（Basic Auth 凭证）—— 用于 YouTube 搜索和字幕
- 一个 [Serper API](https://serper.dev/) key（有免费额度）—— 用于搜索
- 一个 [Jina AI](https://jina.ai/) API key（可选，但推荐）—— 用于网页内容提取
- 一个 LLM API key（例如通过 OpenAI 兼容接口调用的 [Gemini](https://ai.google.dev/)）—— 用于生成和翻译

### 安装

```bash
git clone https://github.com/declanliang/game-wiki-template-all.git
cd game-wiki-template-all/seoscout
pip install -e .
```

### 配置

```bash
cp .env.example .env
# 编辑 .env，填入你的 API key
```

### 准备关键词文件

创建一个 JSON 文件来描述你的关键词。有两个字段用来描述游戏/产品：

- `game_name` —— 展示名称,用于自动生成项目名/输出目录名。
- `filter_keyword` —— 可选;如果不填,默认使用 `game_name` 的值。有两个作用：
  1. **搜索 query 消歧**（Web + YouTube 都生效）：`filter_keyword` 里有、但关键词本身没有的词，会被自动拼进实际发给 Serper/DataForSEO 的搜索 query 里。比如 `filter_keyword="Roblox My Game"`、某条关键词是 `"My Game secretary"`，实际搜索的 query 会是 `"Roblox My Game secretary"`——多出来的 "Roblox" 让搜索引擎自己的相关性排序知道这是在找游戏内容，而不是事后再从搜到的结果里挑。这是防止游戏名撞现实通用词（比如 "Secretary"、"Nurse" 这类词本身也是常见职业名）最有效的一步,因为不丢结果,只是让搜索本身更精确。
  2. **YouTube 结果宽松过滤**：把 `filter_keyword` 拆成单词后，标题命中**任意一个**词就保留，不要求完整短语逐字匹配（游戏视频标题措辞五花八门，要求完整匹配会把大量真实相关内容也过滤掉）。Web 结果不做这层过滤，Google 排序已经够精确。

  > 即使加了 query 消歧和过滤，如果游戏名本身和现实世界撞名很严重（比如 "Animal Hospital" 本身就是"动物医院"的意思），仍然可能有个别文章在生成阶段写偏——这类"格式正常但主题错了"的问题，`filter_keyword` 解决不了，要靠下面的 `seoscout qa` 步骤兜底。

**分类格式**（自己手动把每个关键词分配到对应类别）：

```json
{
  "game_name": "My Game",
  "languages": ["es", "pt", "de", "fr"],
  "categories": [
    {
      "category": "Guide",
      "keywords": [
        "My Game beginner guide",
        "My Game walkthrough",
        "My Game how to level up fast"
      ]
    },
    {
      "category": "Tier List",
      "keywords": [
        "My Game best characters tier list",
        "My Game best weapons"
      ]
    }
  ]
}
```

**扁平格式**（所有文章放在同一个目录下，不分类）：

```json
{
  "game_name": "My Game",
  "keywords": [
    "My Game beginner guide",
    "My Game best characters tier list",
    "My Game tips and tricks"
  ]
}
```

**扁平 + 自动分类格式**（给一份扁平的关键词列表和一组固定的类别名，让 LLM 把每个关键词分配到对应类别里）：

```json
{
  "game_name": "My Game",
  "category_options": ["Guide", "Tier List", "Codes"],
  "keywords": [
    "My Game beginner guide",
    "My Game best characters tier list",
    "My Game codes 2026"
  ]
}
```

> - 分类格式会把输出组织到子目录中：`articles/en/guide/`、`articles/en/tier-list/` 等 —— 和手动分类格式的效果一致。
> - `category_options` 是可选字段，只有在 `keywords` 是扁平格式、且没有设置 `categories` 时才会生效。设置了它之后，运行 `seoscout classify`（或 `seoscout run`）会用一次 LLM 调用把每个关键词分配到列表里的某个类别——LLM 只会从你给定的固定列表里选，不会自己发明新类别名。
> - `languages` 是可选字段。如果在关键词 JSON 里设置了它，`seoscout run` 会在生成文章后自动翻译成指定语言。如果不设置，`seoscout translate` 需要手动传 `--lang` 参数。

### 运行

```bash
# Step 0：（可选）把扁平关键词列表自动分类
seoscout classify --keywords keywords.json

# Step 1：在 YouTube + Google 上搜索关键词
seoscout search --keywords keywords.json

# Step 2：收集字幕和网页内容
seoscout collect --keywords keywords.json

# Step 3：基于收集到的素材生成文章
seoscout generate --keywords keywords.json

# Step 4：LLM 复核生成的文章是否文不对题，删掉跑题的（必经步骤，见下）
seoscout qa --keywords keywords.json

# Step 5：翻译成其他语言
seoscout translate --keywords keywords.json --lang es,pt,de,fr
```

`seoscout classify` 只有在你使用上面的 `category_options` 自动分类格式时才需要——如果已经手动设置了 `categories`，或者根本没有 `category_options` 字段，这一步是空操作（no-op）。分类完成后，建议先审查/编辑 `classified_keywords.json`，再继续执行 `search`，就像审查 `search_results.json` 一样。

`seoscout qa` 用于抓"文不对题"——游戏名/机制名跟现实世界某个通用概念撞名时（比如一个 Roblox 游戏里的 "Secretary" 职业，跟现实里的"秘书"撞词），生成阶段偶尔会把文章写成真实世界的职业介绍，而不是游戏攻略；这类文章格式、篇幅都正常，`generate` 阶段的结构性校验查不出来，只能靠语义判断。**这一步是流水线的必经步骤，不提供跳过选项**——不跑这一步意味着直接把可能文不对题的内容当成成品，等于让下游（比如接入 wiki 站模板时）来发现问题，那样这一步存在的意义就没有了。判定为跑题的文章会被删除（连同它已有的所有语言翻译一起删），这样 `translate` 就不会浪费钱去翻译一篇要被扔掉的文章。

用一条命令做完 分类（如果适用）+ 搜索 + 收集 + 生成 + QA 复核 + 翻译（如果设置了 `languages`）：

```bash
seoscout run --keywords keywords.json
```

项目名会从关键词文件里的 `game_name` 自动生成（转小写、空格替换为 `_`）。如果没有设置 `game_name`，则使用文件名代替。

> 约定把每个项目的关键词文件放在 `projects/<project_name>/keywords.json`，例如 `projects/my_game/keywords.json`。这样运行后 `OUTPUT_DIR`（默认 `./projects`）会在同一个目录下生成 `out/`、`logs/`、`articles/`，输入和产出都在一个项目文件夹里，方便管理多个项目。

### 拿到一份 keywords.json，怎么在终端跑起来？

如果你已经有一份符合上面 schema 的 JSON 文件（比如从别的关键词工具导出的），但它不在 `projects/` 目录下——`--keywords` 可以指向磁盘上任意路径，不要求文件必须放在 `projects/` 里。以 Windows 为例，假设文件在：

```
C:\Users\you\Downloads\my-game-20260716\keywords.json
```

**推荐做法：先复制进 `projects/`，再跑**（和已有项目保持同样的目录习惯，产出也会更整齐）：

```bash
# 1. 进入 seoscout 目录
cd C:\path\to\seoscout

# 2. 建一个项目文件夹（文件夹名随意，实际项目名以 keywords.json 里的 game_name 为准）
mkdir projects\my_game

# 3. 把文件复制进去
copy "C:\Users\you\Downloads\my-game-20260716\keywords.json" projects\my_game\keywords.json

# 4. 跑完整流程
python -m seoscout.cli run --keywords projects/my_game/keywords.json
```

**也可以不复制，直接指向原始文件**——产出照样会生成在 `projects/<game_name>/` 下（由 `game_name` 决定，和 `--keywords` 参数指向哪里无关）：

```bash
python -m seoscout.cli run --keywords "C:\Users\you\Downloads\my-game-20260716\keywords.json"
```

**关于 JSON 格式的两个常见坑**：
- 字段必须是 `game_name`，不是 `topic_name`——早期版本用的是 `topic_name`，如果你的关键词是用旧工具/旧脚本生成的，先检查一下这个字段名，改错了 `seoscout` 会读不到游戏名，项目名会退化成用文件名生成。
- 想要多语言输出，记得在 JSON 里加 `"languages": ["es", "pt", ...]`，否则 `run` 会在 `qa` 之后直接结束，不会有翻译产出（`seoscout translate` 本身可以后续单独补跑，加 `--lang` 参数）。

运行过程中终端会实时打印每个 Step 的进度和最终统计，跑完直接去 `projects/<project_name>/articles/` 下取产出即可。

也可以作为 Python 模块使用：

```bash
python -m seoscout run --keywords keywords.json
```

## 工作原理

```
keywords.json
     │
     ▼
┌─────────────────────────────┐
│  seoscout classify（可选）    │  ← 只有设置了 category_options 才会运行
│    扁平关键词 + 固定           │
│    类别列表 → LLM             │
│    classified_keywords.json  │
└─────────────────────────────┘
              │
              ▼
┌─────────────────────────────┐
│  seoscout search             │  ← 项目名自动来自 game_name
│  ┌───────────┐ ┌──────────┐ │
│  │  YouTube   │ │  Google  │ │
│  │(DataForSEO)│ │ (Serper) │ │
│  └─────┬─────┘ └────┬─────┘ │
│        └──────┬──────┘       │
│               ▼              │
│    search_results.json       │
│    （审查 & 过滤）             │
└─────────────────────────────┘
              │
              ▼
┌─────────────────────────────┐
│  seoscout collect            │
│  ┌───────────┐ ┌──────────┐ │
│  │  YouTube   │ │   Web    │ │
│  │   字幕     │ │  (Jina)  │ │
│  └─────┬─────┘ └────┬─────┘ │
│        └──────┬──────┘       │
│               ▼              │
│     collected/*.json         │
│     （按关键词整理的素材）      │
└─────────────────────────────┘
              │
              ▼
┌─────────────────────────────┐
│  seoscout generate           │
│        ┌──────────┐          │
│        │   LLM    │          │
│        └────┬─────┘          │
│             ▼                │
│     articles/en/*.mdx        │
│     （带 JS export metadata  │
│      的 MDX 文章）             │
└─────────────────────────────┘
              │
              ▼
┌─────────────────────────────┐
│  seoscout qa（必经步骤）       │  ← LLM 复核每篇是否文不对题
│        ┌──────────┐          │     跑题的连同已有翻译一起删
│        │   LLM    │          │     qa_results.json（缓存）
│        └────┬─────┘          │     qa_removed.jsonl（审计日志）
│             ▼                │
│   （跑题文章已删除）           │
└─────────────────────────────┘
              │
              ▼
┌─────────────────────────────┐
│  seoscout translate          │
│  --lang es,pt,de,fr,ja,...  │
│        ┌──────────┐          │
│        │   LLM    │          │
│        └────┬─────┘          │
│             ▼                │
│  articles/{lang}/*.mdx       │
│  （多语言文章）                │
└─────────────────────────────┘
```

## 输出格式

### classified_keywords.json（Step 0 输出，仅在使用 `category_options` 时产生）

```json
[
  {"keyword": "My Game beginner guide", "category": "Guide"},
  {"keyword": "My Game codes 2026", "category": "Codes"}
]
```

在运行 `seoscout search` 之前，可以手动编辑这里的任意 `category` 值——下次运行时会直接从这个文件读取。

### search_results.json（Step 1 输出）

```json
{
  "version": "2.0",
  "created_at": "2026-06-10T12:00:00",
  "keywords": [
    {
      "keyword": "My Game beginner guide",
      "youtube": {
        "count": 2,
        "items": [
          {
            "title": "My Game Beginner Guide 2026",
            "url": "https://youtube.com/watch?v=xxx",
            "video_id": "xxx",
            "channel": "Gamer",
            "duration": "15:30",
            "duration_seconds": 930,
            "view_count": 50000,
            "selected": true
          }
        ]
      },
      "web": {
        "count": 5,
        "items": [
          {
            "title": "Complete Beginner Guide - My Game Wiki",
            "url": "https://example.com/guide",
            "domain": "example.com",
            "snippet": "Everything you need to know...",
            "selected": true
          }
        ]
      }
    }
  ]
}
```

把不想要的条目设置 `"selected": false`，然后运行 `seoscout collect`。

### collected/*.json（Step 2 输出）

每个关键词一个文件（例如 `my_game_beginner_guide.json`）：

```json
{
  "keyword": "My Game beginner guide",
  "collected_at": "2026-06-10T12:05:00",
  "sources": {
    "youtube": {
      "count": 1,
      "videos": [
        {
          "type": "youtube",
          "title": "My Game Beginner Guide 2026",
          "url": "https://youtube.com/watch?v=xxx",
          "content": "Full transcript text here..."
        }
      ]
    },
    "web": {
      "count": 1,
      "pages": [
        {
          "type": "web",
          "title": "Complete Beginner Guide",
          "url": "https://example.com/guide",
          "content": "Cleaned web page content here..."
        }
      ]
    }
  },
  "total_sources": 2
}
```

### articles/en/*.mdx（Step 3 输出）

每个关键词一个 MDX 文件（例如 `my-game-beginner-guide.mdx`）。使用 JavaScript 的 `export const metadata` 语法，以便兼容 Next.js MDX wiki 项目：

```mdx
export const metadata = {
  title: "My Game Beginner Guide: Everything You Need to Know in 2026",
  description: "Complete beginner guide for My Game with tips, strategies, and walkthrough.",
  category: "guide",
  date: "2026-06-10",
}

<Callout type="info">
**Quick Guide**

- Key takeaway 1
- Key takeaway 2
- Key takeaway 3
</Callout>

## Getting Started

Your article content here...

<Callout type="tip">
**A short, punchy takeaway.**

One or two sentences of extra context for a genuinely useful aside.
</Callout>

## Tips and Tricks

- Tip 1...
- Tip 2...

## FAQ

**Q: Is My Game free to play?**
A: Yes, My Game is...
```

如果使用了分类关键词，文章会被组织到子目录中：`articles/en/guide/`、`articles/en/bosses/`、`articles/en/tier-list/` 等。

开头的 Quick Guide 摘要框是**代码拼装的，不是模型手写的**——模型只输出纯文本 bullet（`QUICKGUIDE:` 部分，详见下方"如何使用自定义 prompt 模板"），`<Callout>` 包装标签由 `_build_mdx()` 确定性拼接，不会出现格式错误。正文中间偶尔出现的 `<Callout type="tip"/"warning"/"success">` 提示框则是模型按需自主插入的（0-2 处），格式经 `templates/generate.md` 里的示例约束，但不是代码强制拼装的。

> ⚠️ **依赖前端渲染支持**：`<Callout type="...">` 是一个自定义 MDX 组件标签，wiki 站点前端需要在自己的 `useMDXComponents()`（或等价的 MDX 组件映射）里注册一个 `Callout` 组件（接收 `type` prop：`info`/`tip`/`warning`/`success`）才能正确渲染，否则页面上会直接把标签当纯文本显示。seoscout 本身不提供前端组件。

### qa_results.json / qa_removed.jsonl（Step 4 输出）

`qa_results.json`——每篇英文文章的复核结果缓存，key 是相对 `articles/en/` 的路径：

```json
{
  "guide/my-game-secretary.mdx": {
    "verdict": "OFF_TOPIC",
    "reason": "The article discusses a real-world profession instead of the game.",
    "checked_at": "2026-07-16T17:36:30.832679"
  },
  "guide/my-game-walkthrough.mdx": {
    "verdict": "ON_TOPIC",
    "reason": "Clearly about the game's mechanics.",
    "checked_at": "2026-07-16T17:36:31.021443"
  }
}
```

已经有结果的文章不会重复花钱复核，除非加 `--overwrite`。

`qa_removed.jsonl`——每条被删除文章的审计日志（追加写入，不会清空），方便事后抽查复核判断是否有误杀/漏杀：

```json
{"slug": "guide/my-game-secretary.mdx", "verdict": "OFF_TOPIC", "reason": "...", "removed_files": ["articles/en/guide/my-game-secretary.mdx", "articles/es/guide/my-game-secretary.mdx"], "removed_at": "2026-07-16T17:36:30.832679"}
```

`removed_files` 列出这次连带删除的所有文件——英文原文加上当时已存在的所有语言翻译版本。

### articles/{lang}/*.mdx（Step 5 输出）

结构和英文文章相同，翻译成目标语言。任意语言代码都支持，常见的有：

| 代码 | 语言 | 代码 | 语言 |
|------|----------|------|----------|
| `es` | 西班牙语 | `ko` | 韩语 |
| `pt` | 葡萄牙语（巴西） | `ru` | 俄语 |
| `de` | 德语 | `zh` | 中文 |
| `fr` | 法语 | `vi` | 越南语 |
| `ja` | 日语 | `th` | 泰语 |
| `ar` | 阿拉伯语 | `id` | 印尼语 |
| `it` | 意大利语 | `tr` | 土耳其语 |
| `pl` | 波兰语 | `nl` | 荷兰语 |
| `hi` | 印地语 | `tl` | 他加禄语 |

## 项目结构（面向开发者 / 接手的 AI）

```
seoscout/
├── cli.py                    # 入口，解析子命令（search/collect/generate/qa/translate/classify/run）
├── classify.py                # Step 0：扁平关键词 + category_options → LLM 自动分类
├── search.py                  # Step 1：调度 YouTube/Web 并行搜索，产出 search_results.json
├── collect.py                  # Step 2：调度字幕/网页内容提取，产出 collected/*.json
├── generate.py                 # Step 3：LLM 生成 MDX 文章
├── qa.py                        # Step 4：LLM 复核文章是否文不对题，删跑题的（必经步骤，不可跳过）
├── translate.py                # Step 5：LLM 翻译文章到目标语言
├── templates/
│   ├── classify.md             # 用 string.Template（$var 语法）
│   ├── generate.md             # 用 str.format()（{var} 语法，模板里的字面 { } 要转义成 {{ }}）
│   ├── qa.md                    # 用 string.Template（$var 语法）
│   └── translate.md            # 用 string.Template（$var 语法）
└── core/
    ├── config.py                # 全局配置单例，Config.init(project) 从 .env 加载并建目录
    ├── models.py                 # YouTubeItem/WebItem/KeywordData 等数据结构
    ├── dataforseo_client.py      # DataForSEO SERP API 客户端（YouTube 搜索 + 字幕）
    ├── youtube.py                 # YouTube 搜索/提取调度（内部调用 dataforseo_client）
    ├── web.py                     # Web 搜索（Serper）+ 提取（Jina）
    ├── llm_client.py              # LLM 客户端，多 key 轮询 + 重试 + 统计
    ├── cleaner.py                 # 网页内容清洗（去导航/广告等噪音）
    └── utils.py                   # JSON 读写、磁盘缓存、URL hash、搜索 query 消歧、
                                    # 文章 metadata 字段提取（translate.py/qa.py 共用）等工具函数
```

### 关键设计事实

- **无数据库，纯文件驱动**。每个项目的状态就是 `projects/<name>/` 下的 JSON 文件 + Markdown 文件，`out/cache/{web,youtube}/` 按 URL hash / video_id 缓存已提取的内容。所有阶段都是幂等的——重新运行会跳过已存在的产出（`collect`/`generate`/`translate` 都有 skip-if-exists 逻辑），可以放心补跑失败项，不会重复消耗 API 额度。
- **`Config` 是一个进程级单例**，每个子命令开始时调用 `Config.init(project)` 从 `.env` 加载配置并创建 `projects/<project>/{out,logs,articles}` 目录。`seoscout run` 会对每个阶段重复调用 `Config.init`，但控制台日志只在第一次调用时被镜像（tee）到 `projects/<name>/logs/seoscout.log`，所以整个 pipeline 共享一份日志文件。
- **YouTube 完全通过 DataForSEO**（`core/dataforseo_client.py`），不使用 yt-dlp、不使用代理 IP、不使用 `youtube_transcript_api`。这是踩过坑之后的结论：yt-dlp + 代理 IP 的方案不稳定（代理商本身会挂，YouTube 也会封锁高频请求字幕的 IP）。Web 搜索（Serper）和内容提取（Jina）都是托管服务，**不需要也没有配置代理**。
- **`filter_keyword` 先做搜索 query 消歧，再做 YouTube 结果的宽松过滤**。`core/utils.py` 的 `build_disambiguated_query()` 会把 `filter_keyword` 里关键词本身没有的词（比如 "Roblox"）拼进实际发给 Serper/DataForSEO 的搜索 query 里——这是主防线，让搜索引擎自己的排序做消歧，不丢结果。YouTube 结果之后还有一层宽松的标题过滤（拆词后任意一个词命中就保留，详见 `youtube.py` 的 `_filter_by_keyword`），Web 结果不做这层过滤。**不要把 YouTube 那层过滤改回完整短语匹配**——这是从真实项目"过滤太严导致产出稀少"的教训里得出的。
- **`seoscout qa` 是文不对题问题的第二道防线，且和游戏/平台无关，是流水线里不可跳过的一步**。第一道防线（query 消歧）解决不了所有情况——某些常见英文词（职业名、地名）本身在 LLM 训练数据里就是极强的现实世界先验，即使参考资料是干净的游戏内容，模型也可能想歪。`qa.py` 用一次独立的 LLM 调用复核每篇生成的英文文章"内容是不是真的在讲这个游戏"，prompt 里只传 `game_name`，不写死任何具体游戏/平台名称，可以直接套用到任何项目。判定跑题就删——英文原文加上它当时已有的所有语言翻译一起删（避免留下孤立的旧翻译），删除记录写入 `out/qa_removed.jsonl` 方便事后抽查，结果缓存在 `out/qa_results.json`（`--overwrite` 才会重新复核）。`seoscout run` 里这一步没有跳过选项——不跑等于把可能文不对题的内容直接当成品交付，这一步存在的意义就是不允许这种情况发生。
- **开头 Quick Guide 摘要框和正文提示框走的是两条不同的信任路径**。`generate.py` 的输出契约里，`QUICKGUIDE:` 部分只允许模型给纯文本 bullet，`<Callout type="info">...</Callout>` 的包装标签由 `_build_mdx()` 用代码确定性拼接——这是这个项目一贯的原则（`export const metadata` 块也是同样处理）：不让模型手写它容易写错的包装语法。但正文中间的 `<Callout type="tip"/"warning"/"success">` 提示框，因为位置由上下文决定、Python 没法预先知道该插在哪，只能靠模型自己按 `templates/generate.md` 里的示例直接写在 body 里，格式风险比 Quick Guide 更高，但即使模型写错了标签也只是渲染成一段普通文本，不会破坏整篇文章的校验。
- **LLM 请求支持多 key 轮询**（`.env` 里配 `LLM_API_KEY_1`/`_2`/`_3`...），`LLMClient._next_key()` 按请求顺序轮询，每次重试也会换下一个 key。这是为了缓解第三方 LLM 网关的限速和瞬时错误（`429`/`500`/`524`），不是为了绕过官方限额。
- **`projects/` 下的每个子目录是一个独立项目**：`keywords.json`（用户提供的输入，会被 git 追踪）+ `out/`、`logs/`、`articles/`（运行产出，被 `.gitignore` 忽略）。`examples/keywords_sample.json` 是给新用户看的 schema 示例，不是真实项目。`doc/` 目录存放重大技术决策的设计文档（比如 DataForSEO 迁移方案），做架构级改动前建议先看一眼有没有相关文档。

## 配置参考

所有配置都在 `.env` 中（从 `.env.example` 复制后填入你的 key）：

```bash
cp .env.example .env
```

### 🔑 必需 —— API Key

使用 seoscout 至少需要一个 API key：

```bash
# 通过 Serper 进行 Google 搜索 —— 必需
# 在 https://serper.dev/ 获取免费 key
SERPER_API_KEY=your_serper_api_key_here

# 通过 Jina 提取网页内容 —— 推荐
# 不填也能用，但速率限制会更低
# 在 https://jina.ai/ 获取免费 key
JINA_API_KEY=your_jina_api_key_here
```

| 变量 | 是否必需 | 获取地址 |
|----------|:--------:|--------------|
| `SERPER_API_KEY` | ✅ 必需 | [serper.dev](https://serper.dev/)（有免费额度） |
| `JINA_API_KEY` | 推荐 | [jina.ai](https://jina.ai/)（有免费额度） |
| `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` | ✅ 必需（YouTube 搜索/字幕） | [dataforseo.com](https://app.dataforseo.com/api-dashboard) Basic Auth 凭证 |
| `LLM_API_KEY_1`（可加 `_2`、`_3`...） | 用于生成/翻译 | 任意 OpenAI 兼容接口（Gemini、OpenAI 等）；配置多个 key 会自动轮询，分摊限速 |

### 📁 输出

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `OUTPUT_DIR` | `./projects` | 所有项目数据的根目录。约定每个项目一个子目录（如 `projects/my_game/`），`keywords.json` 输入文件和 `out/`、`logs/`、`articles/` 产出放在一起 |

### 🎬 YouTube —— DataForSEO

`seoscout search`/`collect` 的 YouTube 环节需要。搜索和字幕都走 [DataForSEO](https://app.dataforseo.com/api-dashboard) 的 SERP API，不使用 yt-dlp，也不需要代理 IP。

```bash
DATAFORSEO_LOGIN=your_login
DATAFORSEO_PASSWORD=your_password
```

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `DATAFORSEO_LOGIN` | _(空)_ | DataForSEO 账号的 Basic Auth 用户名 |
| `DATAFORSEO_PASSWORD` | _(空)_ | DataForSEO 账号的 Basic Auth 密码 |
| `DATAFORSEO_BASE_URL` | `https://api.dataforseo.com` | API 地址，一般不用改 |
| `YOUTUBE_LOCATION_CODE` | `2840` | 搜索地区代码（`2840` = 美国） |
| `YOUTUBE_LANGUAGE_CODE` | `en` | 搜索语言代码 |
| `YOUTUBE_DEVICE` / `YOUTUBE_OS` | `desktop` / `windows` | 模拟的设备类型 |
| `YOUTUBE_BLOCK_DEPTH` | `10` | 每次搜索请求返回的结果深度（越大越贵，`collect` 阶段本来就只取每个关键词 Top-K，没必要设太大） |
| `YOUTUBE_MAX_DURATION` | `3600` | 超过此时长（秒）的视频会被跳过 |
| `YOUTUBE_EXTRACT_TOP_K` | `1` | 每个关键词提取的字幕数量 |
| `YOUTUBE_SEARCH_WORKERS` | `3` | 并行搜索的 worker 数（受 DataForSEO 账号并发上限约束） |
| `YOUTUBE_TRANSCRIPT_WORKERS` | `5` | 并行提取字幕的 worker 数 |

### 🌍 Web 调优

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `WEB_SEARCH_TOP_N` | `10` | 每个关键词的 Google 搜索结果数 |
| `WEB_EXTRACT_TOP_K` | `1` | 每个关键词提取的页面数 |
| `WEB_SEARCH_CONCURRENCY` | `5` | Serper API 并发数 |
| `JINA_RPM` | `200` | Jina 速率限制（每分钟请求数） |
| `JINA_CONCURRENCY` | `20` | Jina 并行请求数 |
| `WEB_EXTRACT_RETRIES` | `3` | 网页提取重试次数 |

### 🤖 LLM —— 用于生成 & 翻译

`seoscout generate` 和 `seoscout translate` 需要。任意 OpenAI 兼容接口都可以（Gemini、OpenAI、DeepSeek 等）。

支持配置多个 key（`LLM_API_KEY_1`、`_2`、`_3`...），请求会在这些 key 之间轮询，用来分摊限速和瞬时错误——LLM 网关偶尔会返回 `429`/`500`/`524` 这类瞬时错误，key 越多，单个 key 被限速的概率越低，整体吞吐越稳定。只有一个 key 也没问题，只填 `LLM_API_KEY_1` 即可。

```bash
LLM_API_KEY_1=your_api_key
LLM_API_KEY_2=your_second_api_key   # 可选，继续加 _3、_4...
LLM_API_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
LLM_MAX_TOKENS=10000
```

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `LLM_API_KEY_1`（可加 `_2`、`_3`...） | _(空)_ | LLM 的 API key，可配置多个用于轮询 |
| `LLM_API_BASE_URL` | _(需设置)_ | OpenAI 兼容接口地址 |
| `LLM_MODEL` | `gemini-2.5-flash` | 模型名称 |
| `LLM_TEMPERATURE` | `0.7` | 采样温度 |
| `LLM_MAX_TOKENS` | `10000` | 单次请求的最大输出 token 数（约一篇 1600 词文章 + 几个表格的量；调太大会让模型一旦进入重复输出的退化循环时能跑更远，见下方"生成内容异常膨胀"） |
| `LLM_FREQUENCY_PENALTY` | `0.3` | 抑制重复 token 的惩罚系数，降低表格生成时陷入复读循环的概率 |
| `LLM_PRESENCE_PENALTY` | `0.3` | 抑制重复主题的惩罚系数，同上 |
| `LLM_TIMEOUT` | `300` | 请求超时时间（秒） |
| `LLM_RETRY_ATTEMPTS` | `2` | 失败重试次数（每次重试会换下一个 key） |
| `LLM_RETRY_DELAY` | `5` | 重试间隔（秒） |

### ⚡ 并发 —— 生成 & 翻译

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `GENERATE_BATCH_SIZE` | `100` | 每批并行生成的文章数 |
| `GENERATE_CONCURRENT_LIMIT` | `10` | 生成阶段最大并发请求数 |
| `TRANSLATE_BATCH_SIZE` | `10` | 每批并行翻译数 |
| `TRANSLATE_BATCH_DELAY` | `1` | 翻译批次之间的间隔（秒） |

### ⚙️ 通用

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `SEARCH_MAX_RETRIES` | `3` | 搜索重试次数 |
| `SEARCH_RETRY_DELAY` | `2` | 重试间隔（秒） |
| `BLOCKED_DOMAINS` | `youtube.com,youtu.be,...` | 从网页结果中排除的域名 |

## 常见问题

### YouTube 搜索/字幕提取失败

检查 `DATAFORSEO_LOGIN`/`DATAFORSEO_PASSWORD` 是否正确（[app.dataforseo.com](https://app.dataforseo.com/api-dashboard) 的 Basic Auth 凭证，不是 API key）；账户余额是否充足；`YOUTUBE_SEARCH_WORKERS`/`YOUTUBE_TRANSCRIPT_WORKERS` 并发是否超过账户限制（可调低）。视频本身没有字幕（`无可用字幕`）是正常业务状态，不是错误，不会重试。

### Serper API 报错

- 检查 API key 是否正确
- 免费额度有速率限制，可以调低 `WEB_SEARCH_CONCURRENCY`
- 在 [serper.dev](https://serper.dev/) 检查账户余额

### 网页内容过短或为空

部分页面会屏蔽自动抓取。可以尝试：
- 调低 `JINA_CONCURRENCY` 避免触发限速
- 配置 `JINA_API_KEY` 以获得更高的速率限制

### LLM 生成失败或返回空内容

- 检查 `LLM_API_KEY_1`（及 `_2`、`_3`...）是否已设置且有效
- 如果被限速，尝试调低 `GENERATE_BATCH_SIZE` 或 `GENERATE_CONCURRENT_LIMIT`
- 检查 `LLM_MAX_TOKENS` —— 部分模型限制更低
- 查看你所用 API 提供商的状态页面

### 生成的文章体积异常大，或表格里有大段空白/重复内容

这是小/快模型（如 `gemini-2.5-flash`）在生成长表格时偶尔出现的"重复陷阱"退化输出——不是 seoscout 的 bug，`generate.py`/`translate.py` 都没有任何表格对齐/填充的后处理逻辑。`validate_markdown()` 已经内置了检测（单文件超过 50,000 字符、`export const metadata` 出现次数不为 1、或存在异常长的连续空白/重复片段，都会判定为无效并触发自动重新生成）。如果仍然偶尔出现：
- 确认 `.env` 里配置了 `LLM_FREQUENCY_PENALTY`/`LLM_PRESENCE_PENALTY`（默认 `0.3`），可以适当调高（如 `0.5`）进一步降低复读概率
- 确认所用的 LLM 网关支持 `frequency_penalty`/`presence_penalty` 这两个字段——少数 OpenAI 兼容代理会拒绝未知字段导致请求报错，如遇到可以把这两个值改回 `0` 关闭

### 如何使用自定义 prompt 模板？

给 `classify`、`generate`、`qa` 或 `translate` 传 `--prompt /path/to/your/prompt.md`。classify 模板使用 `$game_name`、`$category_options`、`$keywords_json` 变量；generate 模板使用 `{merged_data}`、`{current_date}`、`{category}` 变量（模型输出 `TITLE:`/`DESCRIPTION:`/`QUICKGUIDE:`（可选）/`BODY:` 四段文本——`QUICKGUIDE:` 是 3-5 条纯文本 bullet，用于开头的 Quick Guide 摘要框，省略也不会导致校验失败；`export const metadata` 块和 Quick Guide 的 `<Callout>` 包装都由代码拼装，不需要在模板里写 JS/JSX 语法）；qa 模板使用 `$game_name`、`$title`、`$body` 变量，模型只输出 `VERDICT:`/`REASON:` 两行；translate 模板使用 `$language_name`、`$lang_code`、`$title`、`$description`、`$body` 变量，输出格式和 generate 一致（不含 `QUICKGUIDE:` ——那部分已经在英文 body 里以 `<Callout>` 形式存在，翻译时按第 8 条规则原样保留标签、翻译内部文字）。

### 可以用 OpenAI / DeepSeek 等其他模型吗？

可以 —— seoscout 使用的是 OpenAI 兼容的 chat completions 接口。设置 `LLM_API_BASE_URL` 和 `LLM_MODEL` 匹配你的服务商即可：

```bash
# OpenAI
LLM_API_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# DeepSeek
LLM_API_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

## License

[MIT](LICENSE)
