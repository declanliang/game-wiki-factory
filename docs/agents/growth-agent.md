# 飞书游戏管理员中的 GSC Growth 职责

站点上线后的 Growth 职责由飞书账号 `cli_aad59e06a3fa5bee` 绑定的现有
`agent-ff5e1a69`（游戏管理员）承担，不再维护独立 `game-wiki-growth` Agent：

- `game-wiki-operator`：输入游戏信息，创建新站并交付 Cloudflare Workers Static Assets。
- `agent-ff5e1a69` 的 Growth 专项：读取 GSC 数据，给一个已上线站点制定关键词/页面优化方案；用户批准或命中预先允许的高置信规则后，提交 Factory 后台 `siteGrowthContent` 任务，由 Worker 实际生成文章、push Private repo 并部署。

它不修改 Factory、不接触广告、不修改 Cloudflare 环境变量或域名，也不直接 push 游戏仓库。最终写文件、GitHub push 和 Cloudflare Workers Static Assets 发布仍由 Factory Worker 执行，避免多个 Agent 对同一站点并发写入。

Factory 新站默认只生成并发布英语。西班牙语、德语、法语、日语等后续语言由 Growth Agent 根据 GSC/GSA 的“查询语言 + 国家 + 当前排名页面”共同判断；国家流量本身不构成翻译依据。用户批准后，它只扩展现有 Private repo，不重建站点、repo、Worker 或域名。

## 服务器部署

将 Growth 规则作为专项附录同步到现有游戏管理员 workspace，不覆盖其原有
CloudBase、开发和外链规则：

```bash
cp /srv/game-wiki-factory/app/deploy/openclaw-growth/AGENTS.md \
  /home/ubuntu/.openclaw/workspace/agent-ff5e1a69/GAME-WIKI-GROWTH.md
cp /srv/game-wiki-factory/app/deploy/openclaw-growth/GROWTH-RUNBOOK.md \
  /home/ubuntu/.openclaw/workspace/agent-ff5e1a69/GROWTH-RUNBOOK.md
openclaw agents list --bindings
```

该 Agent 已绑定飞书 `cli_aad59e06a3fa5bee`。本地验收时使用现有 Agent ID：

```bash
openclaw agent --local --agent agent-ff5e1a69 \
  --session-key agent:agent-ff5e1a69:growth-audit-<site>-<date> \
  --message '只做只读审计：读取我提供的 GSC 导出和站点，不要修改 repo；输出 growth-plan。'
```

不得把 `cli_aad59e06a3fa5bee` 改绑给 Factory Operator；新站生产仍由另一个飞书
账号绑定的 `game-wiki-operator` 负责。

## 每次给 Agent 的输入

至少提供：

1. 线上域名；
2. 对应 Private GitHub repo 或本地 checkout；
3. GSC 的 7 天、28 天导出，最好再加 90 天；
4. 本轮只读分析，还是已经批准某个 `growth-plan.json` 或其中的机会条目。

推荐首次 Prompt：

```text
请只读审计这个站点。以 GSC 页面总量为准，查询表可能因匿名化不完整。
按一个真实玩家决策聚类，识别 404 排名页、位置 4–15、低 CTR、关键词互相竞争和缺页机会。
允许页面共享少量游戏背景，但每个建议页面必须有独立主答案。
先输出 growth-plan，不要改代码、不要 push。
```

批准后：

```text
我批准 growth-plan 中的 [条目 ID]。请转换为 Factory `siteGrowthContent`
任务并提交后台队列。不要直接修改 repo、不要直接 push、不要直接部署。
提交后报告 Job ID；完成后报告新增 URL、Private repo commit、Worker 线上验证和 14 天后的复盘日期。
```

## Growth plan 最小字段

```json
{
  "site": "https://example.wiki",
  "exportedAt": "2026-07-28",
  "opportunities": [
    {
      "id": "opp-001",
      "primaryQuery": "game best unit",
      "currentUrls": ["/en/tier-list/game-tier-list"],
      "decision": "improve-existing",
      "userQuestion": "Which unit should I invest in now?",
      "mustAnswer": ["ranking basis", "best choices", "alternatives"],
      "sharedContextAllowed": ["unit acquisition basics"],
      "evidenceUrls": ["https://official.example/"],
      "gsc": {"clicks": 0, "impressions": 0, "ctr": 0, "position": 0}
    }
  ]
}
```

Growth Agent 可以提出页面扩展，但不能绕过事实证据、风险过滤和人工批准。

## 可执行任务：siteGrowthContent

`siteGrowthContent` 是 Agent3 真正“产生文章”的稳定接口。它只面向已经存在的站点 workspace，不创建新站、不重建 Basic Info、不重跑 Guide Search，不做翻译。当前版本只支持英文新增文章。

提交示例：

```json
{
  "schemaVersion": 1,
  "taskType": "siteGrowthContent",
  "slug": "my-game",
  "siteUrl": "https://my-game.example",
  "githubRepo": "declanliang/my-game",
  "source": "agent-ff5e1a69:gsc",
  "publish": true,
  "proposals": [
    {
      "action": "create_article",
      "keyword": "My Game late game guide",
      "targetCategory": "guide",
      "intent": "What should a player do first after reaching late game?",
      "reason": "GSC shows impressions for this query family but no dedicated page.",
      "evidence": {
        "clicks28d": 12,
        "impressions28d": 640,
        "avgPosition28d": 11.8,
        "confidence": "high",
        "urls": ["https://official.example/guide"]
      }
    }
  ]
}
```

提交命令：

```bash
/usr/local/bin/gamewiki jobs submit --config /path/to/growth.json
```

字段规则：

- `slug`：必填，必须对应已有站点 workspace，例如 `/srv/game-wiki-factory/workspaces/<slug>`。
- `siteUrl`：建议填写正式域名；发布器会用它设置/验证 canonical origin。
- `githubRepo`：可选但建议填写，格式 `owner/repo`；不填时发布器使用现有 origin。
- `publish`：默认 `true`。设为 `false` 时只生成和本地构建，不 push/部署。
- `proposals`：每次最多 5 条，避免一次 Growth 任务成本失控。
- `action`：当前只能是 `create_article`。
- `targetCategory`：必须是该站 `intake/site-plan.json` 中已经 `published` 的分类；Agent3 不得在这个任务里新增导航分类。
- `keyword`：一个真实搜索意图对应一个页面，可以包含自然变体，但不能把多个不相干需求塞进同一页。

任务执行后会：

1. 生成 `.gamewiki/growth/<timestamp>/growth-seo-keywords.json`；
2. 调用 SEO Scout 搜索、收集、英文文章生成和 QA；
3. 只接入通过 QA 的 `en/<category>/<slug>.mdx`；
4. 更新 `intake/site-plan.json` 的关键词/主题记录；
5. 运行模板 `launch:site`，刷新首页 `Latest Articles`/精选文章；
6. 如果 `publish=true`，走 Factory 发布器 push Private GitHub 并部署 Cloudflare Workers Static Assets；
7. 把非敏感结果写入 Job result。

失败处理：

- 如果文章因证据不足或 QA 删除，Job 会失败并保留 checkpoint；不要改成不相关内容硬补。
- 如果是 ToAPIs/DataForSEO/Serper/Jina/LLM 瞬时错误，Worker/Supervisor/Agent2 按现有规则续跑。
- 如果目标 workspace 不存在、分类未发布、GitHub/Cloudflare 权限或域名问题失败，升级给维护者或域名 Agent。

## 暂不支持

- 西班牙语或其他语言扩展；
- 新增站点分类/导航；
- 改写已有文章；
- 批量重做整个站点；
- 广告变量、Cloudflare 环境变量或域名绑定专项。
