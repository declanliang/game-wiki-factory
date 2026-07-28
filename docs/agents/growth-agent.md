# 独立 OpenClaw GSC Growth Agent

`game-wiki-growth` 是站点上线后的增长 Agent，不属于 Factory 主生产流程：

- `game-wiki-operator`：输入游戏信息，创建新站并交付 Cloudflare Pages。
- `game-wiki-growth`：读取 GSC 数据，给一个已上线站点制定关键词/页面优化方案；用户批准后才修改该游戏自己的 Private repo。

它不修改 Factory、不接触广告、不修改 Cloudflare 环境变量或域名。

Factory 新站默认只生成英语和西班牙语，英语立即公开，西班牙语第三个自然日公开。德语、法语、日语等后续语言由 Growth Agent 根据 GSC/GSA 的“查询语言 + 国家 + 当前排名页面”共同判断；国家流量本身不构成翻译依据。用户批准后，它只扩展现有 Private repo，不重建站点、repo、Pages 项目或域名。

## 在服务器创建

OpenClaw 官方 CLI 支持为 Agent 指定独立 workspace。以 `ubuntu` 用户执行：

```bash
mkdir -p /home/ubuntu/.openclaw/workspace-game-wiki-growth
cp /srv/game-wiki-factory/app/deploy/openclaw-growth/{AGENTS,SOUL,TOOLS,IDENTITY,GROWTH-RUNBOOK}.md \
  /home/ubuntu/.openclaw/workspace-game-wiki-growth/
openclaw agents add game-wiki-growth \
  --workspace /home/ubuntu/.openclaw/workspace-game-wiki-growth \
  --non-interactive
openclaw agents set-identity --agent game-wiki-growth --from-identity
openclaw agents list
```

不要一开始把现有聊天渠道绑定给它，以免抢占 `game-wiki-operator`。先本地验收：

```bash
openclaw agent --local --agent game-wiki-growth \
  --session-key agent:game-wiki-growth:audit-<site>-<date> \
  --message '只做只读审计：读取我提供的 GSC 导出和站点，不要修改 repo；输出 growth-plan。'
```

根据 [OpenClaw Agent CLI](https://docs.openclaw.ai/cli/agents)，标准创建命令是
`openclaw agents add <id> --workspace <path>`；渠道绑定应在本地验收通过后单独配置。

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
