# Alert state and notification deduplication

OilSignal separates **policy evaluation** from **notification emission**.

A stateless evaluation answers: "Which policies match the current evidence?" A stateful evaluation answers: "Which matching policies have newly transitioned into an active state and should notify someone now?"

## Edge-triggered behavior

Stateful policies persist one row per `policy_id` in the local metadata SQLite database:

- `active`: whether the policy matched on its last evaluation;
- `last_changed_at`: when it most recently moved between active and inactive;
- `last_triggered_at`: when it most recently emitted a new notification;
- `last_as_of`: the most recent market observation date involved in the evaluation.

The state machine is deliberately small:

```text
inactive + no match  -> inactive, no notification
inactive + match     -> active,   notify once
active   + match     -> active,   suppress duplicate
active   + no match  -> inactive, recovery / re-arm
```

After a recovery, a later match notifies again. OilSignal does not treat a continuously true condition as a new alert every time cron runs.

## CLI

`alerts-evaluate` is stateful by default:

```bash
oilsignal alerts-evaluate --rules examples/alerts.example.json --data-dir ./data
```

The output contains `notifications` and an explicit transition for every policy. Use `--stateless` for a dry run that never reads or writes alert state:

```bash
oilsignal alerts-evaluate --rules examples/alerts.example.json --data-dir ./data --stateless
```

## API

- `POST /api/alerts/evaluate` is stateless and safe for previews.
- `POST /api/alerts/evaluate/stateful` persists edge-trigger state and returns only newly activated policies in `notifications`.

Delivery adapters should consume `notifications`, not the broader `triggered` list. This keeps email, Slack, Teams, and future premium delivery integrations from spamming users while preserving the complete evaluation audit trail.
