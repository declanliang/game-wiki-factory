# AI / 开发者接手说明

先阅读 `README.md`。本目录是工厂内无具体游戏数据的站点模板；生成后的独立游戏仓库则应提交最终 `intake/`。

## 不可破坏的规则

- 不提交真实游戏的 intake、content、图片、locale 文案或构建输出。
- 分类、六语言标签与分类描述只能读取 `intake/site-plan.json` / `src/config/site-plan.json`。
- 不恢复“扫描 content/en 后用正则改 navigation.ts/content.ts”的旧设计。
- 固定支持 `en/es/de/fr/ja/ko`；非英语缺文案或文章必须失败，不能静默用英文站冒充翻译站。
- 每个页面必须 self-canonical；HTML、sitemap 与 JSON-LD 必须使用相同的 locale-aware URL。
- ingest 必须先清理生成 content，且拒绝 site-plan 未声明的语言/分类。
- 模板脚本必须幂等；同一 intake 连续运行两次结果应一致。

修改后运行所有 `node --check scripts/*.mjs`（至少修改文件）、`npx tsc --noEmit`，并在隔离的具体游戏 site 副本中运行 `npm run launch:site`。
