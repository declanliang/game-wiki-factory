# 故障处理入口

先查同一个 Job 的状态和日志：

```bash
python gamewiki.py jobs status <job-id> --json
python gamewiki.py jobs logs <job-id> --tail 200
```

处理原则：

- 只重试原 Job，复用 checkpoint；不得创建替代任务。
- 不使用 refresh、overwrite、rebuild 或 fullBuild，除非用户明确授权重新付费。
- API 余额/额度问题进入共享 `quota_wait`，只发一条包含供应商、端点和凭据组的告警。
- 内容结构失败先修复对应 checkpoint；代码、schema、身份、GitHub/Cloudflare 和构建问题交给 Codex。
- 服务器工作树不热修。修复必须从 Factory Git 提交部署。

完整分类、恢复白名单和命令见 `../runbook.md` 与 `background-jobs.md`。
