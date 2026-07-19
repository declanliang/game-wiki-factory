# Roblox 游戏基础配置自动化

输入一个 Roblox 游戏名，自动生成 Wiki 首页所需的事实、文案、模块、来源证据、Hero 图片和 favicon 图标包。

项目已经用 Anime Expeditions、Anime Paradox X 与 PursuitCore 完整跑通。当前只支持 Roblox。

本模块位于 `game-wiki-factory/pipeline/basic-info/`。通常由根目录 `python gamewiki.py "GAME NAME"` 调用；只有开发或单独调试 Basic Info 时才直接进入本目录。

## 快速开始

### 1. 安装

需要 Python 3.11 或更高版本。

```powershell
cd path\to\game-wiki-factory\pipeline\basic-info
python -m pip install -e .
```

### 2. 配置 API Key

项目自动读取根目录 `.env`：

```dotenv
TOAPIS_API_KEY=你的 ToAPIs Key

# 可选：仅在 ToAPIs 联网研究失败时降级使用
PERPLEXITY_API_KEY=你的 Perplexity Key
```

现有变量名 `toapis_API_KEY`、`toapis_api_key` 和 `perplexity_api_key` 也兼容。OpenRouter 已完全退出运行链。不要提交或分享 `.env`。

完整配置见 [.env.example](.env.example)。

### 3. 运行

```powershell
python -m gamewiki_automation "Anime Expeditions"
```

一次处理多个游戏：

```powershell
python -m gamewiki_automation "Anime Expeditions" "PursuitCore"
```

指定输出目录：

```powershell
python -m gamewiki_automation "PursuitCore" --output-dir .\my-output
```

强制忽略缓存：

```powershell
python -m gamewiki_automation "PursuitCore" --refresh
```

`--refresh` 会重新产生联网和模型费用，普通运行不要使用。

## 能生成什么

```text
output/<game-slug>/
├── 00基础信息.md             给人阅读的完整报告
├── 00首页信息.json           内部完整首页研究配置
├── 00首页模块.json           4–8 个内容模块研究结果
├── site-identity.json        模板站点身份输入的便捷副本
├── site-content.json         模板首页文案输入的便捷副本
├── template-validation-report.json
├── facts.json                规范化事实中心
├── evidence.json             来源和字段级证据
├── validation-report.json    校验、费用、耗时和 warning
├── raw/                      每个上游任务的原始结构化结果
├── assets/                   内部素材候选与转换记录
    ├── media.json
    ├── hero/                 已验证并下载的 Hero 图片
    └── favicon/              PNG、ICO 和 site.webmanifest
└── template-intake/          最终可直接复制的完整交付包
    ├── site-identity.json    7 个规范大写 key（含 LANGUAGES）
    ├── site-content.json     与 identity 同级；顶层仅 site/home
    ├── site-content.es.json  LANGUAGES 每个非英语代码各一份
    ├── hero.png              唯一一张 Hero（后缀按源图保留）
    └── favicon/              规范要求的 7 个文件
```

`template-intake/` 是唯一需要交给生成网站根目录 `intake/` 的 Basic Info 产物。顶层包含两个基础 JSON、`LANGUAGES` 中每个非英语语言对应的 `site-content.<locale>.json`、一张 `hero.<ext>` 和一个 `favicon/` 文件夹。`assets/` 中的多张图片、`source-icon.png` 和 `media.json` 只用于内部审计，不要复制给模板。

`output/` 和 `.cache/` 都是本地运行目录，不提交到 Git：前者可能包含大量图片和研究结果，后者可能包含付费 API 响应缓存。需要分享某个游戏时，只复制对应的 `output/<slug>/template-intake/`。

`00首页信息.json` 和 `00首页模块.json` 是内部研究/审计产物，不能直接交给模板的 `apply:content`。调试时再读取 `facts.json`、`evidence.json`、`raw/`。

```powershell
# 一次复制完整模板输入（基础 JSON + 本地化 JSON + Hero + favicon）
Copy-Item .\output\anime-expeditions\template-intake\* `
  C:\Users\liang\Documents\Games\anime-expeditions\intake -Recurse -Force

# 只为旧产物重建模板文件，不调用 LLM
python -m gamewiki_automation.template_contract output\anime-expeditions
```

## 工作流程

```text
游戏名
  ↓
Roblox Discover 搜索候选
  ↓
Place / Universe 身份确认
  ↓
Roblox API 官方事实与缩略图
  ↓
ToAPIs Responses API + web_search_preview 联网研究外部官方资源
  ↓（失败时才用 Perplexity）
事实与证据合并、URL 检查
  ↓
应用固定产品语言策略 en/es/de/fr/ja/ko（不调用调研 API）
  ↓
关闭联网生成首页配置
  ↓
按 LANGUAGES 为每个非英语语言生成母语化首页文案
  ↓
递归校验字段树、数组、数字事实及 href/category 一致性
  ↓
联网生成 4–8 个首页模块
  ↓
下载媒体、转换 favicon
  ↓
Schema + 业务规则验证
  ↓
确定性转换为 game-wiki-template 的基础及本地化 intake JSON
  ↓
模板契约 Schema + 事实一致性强校验
```

关键边界：

- Roblox API 已确认的 Place、Universe、创建者和动态数据不能被模型覆盖。
- 首页文案只能使用已进入 `facts.json` / `evidence.json` 的内容。
- 有至少一个来源支持的第三方兑换码可以进入 `liveTools`，但必须明确显示为 `Community-reported active`；无来源、`unknown` 或过期兑换码不会输出。
- Fandom、wiki.gg、fextralife 和竞对 Wiki 不能进入前台 references。
- 资料不足时允许 warning、空字段或少于 8 个模块，不为凑数编造内容。
- Tavily 已从代码、配置和降级链完全移除。
- 模板 JSON 的执行格式不依赖 LLM 自报正确：程序确定性组包，并对基础及本地化对象使用 `additionalProperties: false` 的严格 Schema。
- `site-identity.json` 只允许规范中的 7 个大写 key。语言策略是固定的 `en/es/de/fr/ja/ko`，不再为具体游戏调研语言市场；`site-content.json` 顶层只能是 `site/home`。
- `LANGUAGES` 每声明一个非英语语言，最终包必须包含对应的 `site-content.<locale>.json`。它与英文版必须拥有完全相同的 key、数组长度和顺序；`href`、`*Href`、`category` 以及代码等标识符不得变化。缺文件、结构漂移、数字事实丢失或大段照抄英文都会使模板契约失败。
- `themeColor/modules/displayType/home.start` 等旧字段，以及 Hero 自动字段，会被强校验直接拒绝。
- 模板契约失败会把整次运行标记为 `fail`，不能进入自动导入。

## 验证状态

- `pass`：身份、Schema、URL 和业务规则通过。
- `warning`：结构可用，但存在明确的不确定内容，需要人工决定是否上线。
- `fail`：身份不确定、Schema 错误、核心 URL 错误或禁止来源；命令退出码为 1。

`warning` 的命令退出码为 0，方便继续生成草稿。上线前必须查看 `validation-report.json`。

## 已验收样本

|游戏|Place ID|结果|备注|
|---|---:|---|---|
|Anime Expeditions|84515722934860|warning|结构正确；兑换码只有第三方佐证|
|Anime Paradox X|76806550943352|warning|`en/es` 本地化模板契约通过|
|PursuitCore|121903154323395|warning|自动发现并排除 Linktree 中旧 Place 84498985865861；本地化模板契约通过|

详细数据见 [验收报告](docs/testing/验收报告.md)。

## 配置项

|环境变量|默认值|说明|
|---|---|---|
|`TOAPIS_API_KEY`|无|默认流程必需|
|`PERPLEXITY_API_KEY`|无|联网研究失败时的备用 Key|
|`TOAPIS_MODEL`|`gpt-5.3-codex-official`|非联网生成模型，必须支持 Responses API|
|`TOAPIS_WEB_MODEL`|`gpt-5.3-codex-official`|联网模型；默认值已实测支持 `web_search_preview`|
|`TOAPIS_REASONING_EFFORT`|`low`|Responses API 推理力度|
|`PERPLEXITY_MODEL`|`sonar-pro`|备用模型|
|`GAMEWIKI_OUTPUT_DIR`|`output`|输出目录|
|`GAMEWIKI_CACHE_DIR`|`.cache`|HTTP 和模型缓存|
|`GAMEWIKI_REQUEST_TIMEOUT`|`300`|模型请求超时秒数|

## 缓存与费用

HTTP 和模型任务分别缓存。ToAPIs 使用独立缓存命名空间，不会误用旧 OpenRouter 响应；事实没有变化时，重复运行不会再次调用模型。

由于提供商和缓存键已经迁移，升级后的第一次完整运行会调用 ToAPIs，即使没有使用 `--refresh`；成功后才会建立新的 ToAPIs 缓存。

实测 PursuitCore 缓存运行：

```text
external_research cached=true
language_market_research cached=true
homepage_config   cached=true
homepage_modules  cached=true
本次费用           $0
总耗时             约 5 秒
```

删除 `.cache/` 或使用 `--refresh` 会重新产生费用。

## 测试

```powershell
python -m compileall -q src tests
python -m unittest discover -s tests -v
```

仓库不提交 `output/`，因此新克隆环境中两个真实产物回归测试会自动跳过；运行一次对应游戏后再执行测试，即会同时检查生成产物。开发时修改 Schema、Prompt 或缓存键后，必须运行：

```powershell
python -m gamewiki_automation "Anime Expeditions" "PursuitCore"
python -m unittest discover -s tests -v
```

当前测试覆盖：

- Roblox 候选评分和身份选择
- JSON 清理与三套 Schema
- ToAPIs Responses 混合输出解析、联网工具和本地 Schema 校验
- 缓存上下文稳定性
- 模块展示类型语义修正
- Anime Expeditions / PursuitCore 真实产物回归
- game-wiki-template 基础及本地化文件的 key 白名单、Hero stats、FAQ、占位符、结构同构、路径和事实一致性契约
- 模板契约失败时正式文件不会残留的阻断测试

## 项目目录

```text
.
├── README.md              使用入口
├── AGENTS.md              AI / 开发者接手说明
├── pyproject.toml         Python 包与命令入口
├── requirements.txt
├── src/gamewiki_automation/
├── tests/
├── docs/                  分类后的项目文档
├── schemas/               设计阶段统一审计 Schema 说明
├── output/                已生成游戏结果（不提交）
└── .cache/                HTTP / 模型缓存（不提交）
```

源码模块职责与文档导航见 [docs/README.md](docs/README.md)。

## 当前仍有的问题

项目可以使用，但不等于所有数据都可以无人审核上线。当前主要限制包括：

- 游戏身份发现依赖 Roblox Discover 页面与 Jina Reader 可用性。
- ToAPIs Responses API 的联网探针和响应解析已经实测；完整双样本产物仍是迁移前生成、迁移后离线回归验证。
- “官方社群”仍包含模型判断；HTTP 可访问不等于账号所有权百分之百确认。
- 费用只有结果上限保护，没有真正的请求中途美元硬熔断。
- favicon 默认由 Roblox 官方图标转换，不是重新设计的 AI 品牌图标。
- 已通过模板真实 `check-intake.mjs + apply-content.mjs` 的隔离导入测试，但还没有执行完整 `launch:site + build + 页面截图`。

完整问题、影响和建议见 [已知问题](docs/KNOWN_ISSUES.md)。

## 文档入口

- [文档总目录](docs/README.md)
- [原始人工流程](docs/source/第四课、游戏首页、文章页建站数据准备%20副本.md)
- [输出规范与任务拆分](docs/design/首页数据采集自动化-输出规范与任务拆分.md)
- [API 调研与方案](docs/research/游戏基础配置自动化-调研与方案.md)
- [Prompt 契约](docs/prompts/Task-0至4-Prompt契约.md)
- [Anime 网页版基准样本](docs/examples/Anime%20Expeditions%20GPT%20产出示例.md)
- [验收报告](docs/testing/验收报告.md)
- [模板首页契约兼容性报告](docs/testing/模板首页契约兼容性.md)
