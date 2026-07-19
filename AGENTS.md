# AI / 开发者接手说明

先完整阅读 `README.md`、`docs/architecture.md`、`docs/runbook.md`、`docs/ai-handoff.md`，再查看目标子模块自己的 `AGENTS.md`。

## 不可破坏的约束

- 本仓库是唯一工厂源码；真实游戏产物只能写入工厂同级的 `../<slug>/`，游戏目录本身就是 Next.js 根。
- 最终部署输入必须在游戏根 `intake/`；调研、cache、manifest 和日志必须在游戏根 `.gamewiki/`。
- 不读取、打印、复制或提交 `.env` 中的值。
- 默认语言严格为 `en/es/de/fr/ja/ko`，顺序也属于契约。
- Basic Info 的 `game-profile.json` 定义分类候选边界；Guide Search 不能越界创建站点分类。
- `site-plan.json` 是 SEO Scout、intake 和模板的唯一语言/分类声明源。
- 发布质量门槛为 4–8 个分类；不为数量接纳完全不相关的主题。
- 正常续跑先验证 checkpoint，再跳过已完成工作。只有显式 refresh/overwrite 才重复付费调用。
- 每次外部命令都必须写独立日志，失败必须写 `manifest.json` 和 traceback。

## 修改后最低验收

运行根、`pipeline/basic-info`、`pipeline/guide-search` 三套 Python 测试，模板运行 `node --check` 和 `npx tsc --noEmit`。修改跨模块契约时还必须用一个项目做端到端验证。
