# 后台任务系统 AI 接手 Prompt

把下面整段交给新的 AI。不要附带任何密钥。

```text
你要继续完成 Game Wiki Factory 的可恢复后台任务系统、Linux 服务器部署和 OpenClaw 对接。

本地仓库：C:\Users\liang\Documents\Games\game-wiki-factory

开始前必须完整阅读：
1. AGENTS.md
2. README.md
3. docs/architecture.md
4. docs/runbook.md
5. docs/ai-handoff.md
6. docs/background-jobs.md
7. docs/design/background-production-v1.md
8. docs/design/production-automation-v2.md

业务决策：
- 新站和旧站只维护一条 full_build 内容流水线。
- 旧站重新花 API 成本执行最新采集、关键词、文章、翻译和模板。
- 旧站复用现有 GitHub repo 和 Vercel project；不用解决历史代码冲突，新产物替换 repo tracked tree。
- 替换前创建备份 tag；repo 始终 Private；Vercel 原域名和环境变量不得删除。
- OpenClaw 只提交/控制任务，长任务由后台 Worker 执行。
- SERPER_API_KEY_1/2 与 JINA_API_KEY_1/2 是主副 Key，日志不得输出值。

先检查 git status 和已有提交，不要重做已完成工作。读取任务数据库、最新测试结果和服务器部署记录。实现或继续验证：SQLite queue、lease/heartbeat、自动重试、needs_attention、CLI、Worker、fullBuild、旧 repo 替换发布、Key 池、清理、systemd/Docker、OpenClaw game-wiki-operator Agent。

修改后最低验收：
- python -m unittest discover -s tests -v
- python -m unittest discover -s pipeline/basic-info/tests -v
- 设置 PYTHONPATH 后运行 pipeline/guide-search/tests
- template scripts node --check
- template npx tsc --noEmit
- 生产 build
- Worker kill/restart 恢复测试
- mocked 发布替换测试
- OpenClaw 提交/查询/重试端到端测试

服务器 SSH 信息和所有 API Token 只存在 factory 根目录被忽略的 .env。只读取变量名和进程使用值，禁止打印、复制进文档或提交 Git。未知或高风险破坏操作先停下说明；正常实现与已授权服务器部署继续执行。

最终报告必须包含：完成的 commit、测试证据、服务器服务状态、OpenClaw Agent 名称及使用 Prompt、尚未完成事项和第一阻塞点。
```

