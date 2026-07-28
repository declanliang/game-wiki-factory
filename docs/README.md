# Game Wiki Factory 文档导航

本目录只保留当前生产契约、运维事实和版本说明。历史讨论不应被当成操作手册；需要追溯时使用 Git 历史。

## 接手必读

1. `../README.md`
2. `architecture.md`
3. `runbook.md`
4. `ai-handoff.md`
5. 全新环境再读 `bootstrap-from-github.md`

## 当前文档分区

- `contracts/`：输入、内容/SEO 和分批语言发布契约。
- `operations/`：后台队列、服务器部署与故障处理。
- `deployment/`：Git-integrated Cloudflare Pages 唯一发布方式。
- `agents/`：OpenClaw Factory Agent 与独立 Growth Agent 的职责。
- `advertising/`：独立广告 Agent 使用的 Adsterra 环境变量契约；不属于 Factory 主流程。
- `releases/`：每个候选版本的验收边界。
- `design/`：仍有参考价值的设计决策；它们不覆盖上面的生产契约。

游戏产物不需要复制这些 Factory 文档。生成项目只保留运行站点必需的代码、`intake/` 契约文件和 `.gamewiki/` 审计产物。
