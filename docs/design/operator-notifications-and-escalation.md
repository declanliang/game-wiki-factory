# Operator notifications and escalation

Status: implemented locally; production deployment waits for a maintenance window with no running jobs.

## Goals

1. A terminal job transition is not lost when OpenClaw, its chat session, or a channel is offline.
2. Reading a message is not treated as delivery; consumers acknowledge only after the channel succeeds.
3. Worker and OpenClaw handle routine operations, while Factory code defects are escalated to Codex/infrastructure maintenance.

## Data flow

```text
Worker transaction
  -> events
  -> notifications (pending)
  -> OpenClaw cron / future dispatcher
  -> bound chat channel
  -> jobs notifications --ack <id>
```

`attempt.finished` creates an outbox row only for `succeeded`, `failed`, `needs_attention`, and `cancelled`. Retryable transient failures remain visible in attempts/logs but do not produce noisy user notifications before bounded retries are exhausted. Cancelling a queued/waiting job also produces a terminal notification.

The notification payload joins only the non-secret job summary, terminal event detail, persisted acceptance result, and log path. It never returns `config_json`, environment values, raw advertising code, or credentials.

## Consumer contract

```bash
/usr/local/bin/gamewiki jobs notifications --json
/usr/local/bin/gamewiki jobs notifications --ack 12 13
```

- Poll every 2–5 minutes until a channel-specific dispatcher is configured.
- Send each item once per notification ID.
- Acknowledge only after successful delivery.
- Leave failed deliveries pending; do not acknowledge optimistically.
- A daily summary is separate from per-job terminal events.

## Authority boundary

- Worker: bounded retries for classified transient infrastructure/API failures.
- OpenClaw operator: inspect, report, retry/cancel through documented CLI, and correct authoritative user input without changing production logic.
- Codex/infrastructure maintainer: source code, tests, schemas, database/state machine, identity selection, content/QA, publishing, advertising, service configuration, or cost-control changes.

OpenClaw must never hot-edit `/srv/game-wiki-factory/app`, run Git maintenance, edit secrets, or restart services. A suspected code bug stays `needs_attention` until a tested Factory commit is deployed in a maintenance window.

## Production rollout gate

1. Wait until `jobs list --json` contains no `running` jobs.
2. Commit and push the tested local Factory changes.
3. Remove/reconcile any production hotfix, then fast-forward the server to the tested commit.
4. Restart Worker and Control once and verify both active.
5. Create a test terminal event, deliver it through the chosen OpenClaw channel, acknowledge it, and verify the pending list is empty.
6. Only then enable the recurring notification schedule.
