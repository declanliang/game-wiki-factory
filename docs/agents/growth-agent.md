# 飞书游戏管理员中的 GSC Growth 职责

站点上线后的 Growth 职责由飞书账号 `cli_aad59e06a3fa5bee` 绑定的现有
`agent-ff5e1a69`（游戏管理员）承担，不再维护独立 `game-wiki-growth` Agent：

- `game-wiki-operator`：输入游戏信息，创建新站并交付 Cloudflare Workers Static Assets。
- `agent-ff5e1a69` 的 Growth 专项：读取 GSC 数据，给一个已上线站点制定关键词/页面优化方案；用户批准后才修改该游戏自己的 Private repo。

它不修改 Factory、不接触广告、不修改 Cloudflare 环境变量或域名。

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
4. 本轮只读分析，还是已经批准某个 `growth-plan.json`。

推荐首次 Prompt：

```text
请只读审计这个站点。以 GSC 页面总量为准，查询表可能因匿名化不完整。
按一个真实玩家决策聚类，识别 404 排名页、位置 4–15、低 CTR、关键词互相竞争和缺页机会。
允许页面共享少量游戏背景，但每个建议页面必须有独立主答案。
先输出 growth-plan，不要改代码、不要 push。
```

批准后：

```text
我批准 growth-plan 中的 [条目 ID]。只修改这个游戏 repo，保留现有 URL；
如果必须改 URL，要同时提供永久重定向。完成构建和 SEO 验收后再 push main，
并报告 commit、变更 URL、线上验证和 14 天后的复盘日期。
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
