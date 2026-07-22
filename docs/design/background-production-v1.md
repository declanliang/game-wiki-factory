# Background Production V1 实施计划

Status: implementation contract  
Scope: local recovery, Linux deployment, OpenClaw control, unified full rebuild  
Last updated: 2026-07-22

## 决策

1. 新站和旧站共用 `full_build`；不维护另一条旧站内容升级流水线。
2. 旧站可复用 GitHub/Vercel 标识，但新产物替换仓库 tracked tree；发布前创建备份 tag。
3. SQLite + 长驻 Worker 是单服务器第一版；多服务器时才迁移 PostgreSQL/Redis。
4. OpenClaw 是控制面，不承载长任务。
5. 现有 `.gamewiki/manifest.json` 与各模块 checkpoint 继续决定阶段复用，数据库只编排 attempt。

## 里程碑

### M1 文档与契约

- 后台任务运维文档、AI 接手 Prompt、配置 schema、状态与错误分类。
- `.env.example` 增加编号 Serper/Jina、Worker、GitHub/Vercel、OpenClaw 设置。

### M2 本地任务系统

- SQLite schema/migration。
- `submit/list/status/logs/retry/cancel`。
- 原子 lease、过期回收、心跳、取消。
- Worker 子进程、独立日志、退出分类和有界退避。
- `fullBuild` 映射到最新完整刷新参数；retry 不重复刷新已验证 checkpoint。

### M3 发布与 Key 池

- 现有 repo Private 校验、远端备份 tag、孤立本地 Git 历史、force-with-lease 替换 `main`。
- 复用 Vercel project，不删除域名和环境变量。
- Serper/Jina 编号 Key 发现、轮换、quota 冷却，兼容旧单 Key 名。

### M4 测试

- 数据库状态机、lease、重试分类、取消、命令生成。
- mocked GitHub/Vercel 替换发布。
- 根、Basic Info、Guide Search 测试与模板 TypeScript/production build。
- 一个低成本本地任务做 kill/restart 恢复验收。

### M5 Linux 服务器

- 检查 Ubuntu/CPU/RAM/磁盘/Docker/OpenClaw。
- `/srv/game-wiki-factory/{app,data,workspaces,logs,cache}`。
- 私有 `.env`、systemd 服务、logrotate、磁盘守卫。
- Worker 并发从 2 开始，build 并发 1。

### M6 OpenClaw

- 创建 `game-wiki-operator` 专用 Agent。
- 安装最小权限控制工具与 system prompt。
- 提交、查询、retry、cancel 和 needs_attention 汇总验收。
- 关闭 Agent 会话后确认 Worker 继续运行。

## 回滚

- Factory 每个里程碑独立 commit。
- 数据库 migration 只向前增加字段/表，部署前备份 SQLite。
- 旧站覆盖前创建 `pre-rebuild-<UTC>` tag。
- Push 使用 `--force-with-lease`，远端状态变化时安全失败。
- Vercel 只在 GitHub 更新成功后触发，不删除项目配置。

## 完成定义

- 每天可排队 10 个任务，以 2–3 并发后台执行。
- SSH/OpenClaw 会话中断不丢任务。
- 临时错误自动恢复，未知错误可由另一位 AI 只读日志后继续。
- 敏感信息不出现在数据库、Git、日志或 Prompt。
- 文档中的命令与服务器实际服务一致。

