# Alert state, outbox delivery, and notification deduplication

OilSignal separates **policy evaluation**, **notification enqueue**, and **external delivery**.

A stateless evaluation answers: "Which policies match the current evidence?" A stateful evaluation answers: "Which matching policies have newly transitioned into an active state and should become durable notifications now?" Delivery then drains those durable notifications through an adapter.

## Edge-triggered behavior

Stateful policies persist one row per `policy_id` in the local metadata SQLite database:

- `active`: whether the policy matched on its last evaluation;
- `last_changed_at`: when it most recently moved between active and inactive;
- `last_triggered_at`: when it most recently created a new notification;
- `last_as_of`: the most recent market observation date involved in the evaluation.

The state machine is deliberately small:

```text
inactive + no match  -> inactive, no notification
inactive + match     -> active,   enqueue once
active   + match     -> active,   suppress duplicate
active   + no match  -> inactive, recovery / re-arm
```

After a recovery, a later match enqueues again. OilSignal does not treat a continuously true condition as a new alert every time cron runs.

## Transactional outbox

On an inactive-to-active transition, OilSignal writes the alert-state transition and a new `AlertOutboxRow` in the **same SQLite transaction**. This closes the failure window where a process could mark a policy active and then crash before any notification existed.

Each outbox row records:

- a unique `outbox_id` and `policy_id`;
- creation time and market `as_of` date;
- the serialized policy evaluation, including condition audit trace;
- delivery status (`pending`, `failed`, or `delivered`);
- delivery adapter name;
- attempt count and last-attempt time;
- delivery time or the latest bounded error message.

Pending and failed rows remain eligible for later delivery attempts. Delivered rows are no longer returned by the normal outbox-drain query.

## Delivery guarantee

The community outbox is **at least once**, not exactly once.

If a process crashes before an adapter accepts a message, the pending row is retried. If an adapter fails, OilSignal records the failure and retries it later. If a process crashes **after** an external provider accepted the message but **before** OilSignal committed `delivered`, the same outbox row can be attempted again and a duplicate is possible.

Production adapters should therefore use a stable provider idempotency key derived from `outbox_id` whenever the provider supports one. This keeps OilSignal's local state simple and auditable without pretending an external network call can participate in the SQLite transaction.

## CLI

`alerts-evaluate` is stateful by default and atomically enqueues new notifications:

```bash
oilsignal alerts-evaluate --rules examples/alerts.example.json --data-dir ./data
```

The output contains `notifications`, an explicit transition for every policy, and an `outbox_id` for new notifications. Use `--stateless` for a dry run that never reads or writes alert state:

```bash
oilsignal alerts-evaluate --rules examples/alerts.example.json --data-dir ./data --stateless
```

Drain pending/failed outbox rows through the included console adapter:

```bash
oilsignal alerts-deliver --adapter console --data-dir ./data
```

The command returns one delivery receipt per attempted row. It exits non-zero if any attempted row remains failed, making it suitable for cron/systemd monitoring and retry loops.

## API

- `POST /api/alerts/evaluate` is stateless and safe for previews.
- `POST /api/alerts/evaluate/stateful` persists edge-trigger state and atomically enqueues newly activated policies.

External delivery is deliberately separated from the API evaluation request. This keeps a slow or unavailable notification provider from changing the market-evaluation result or rolling back a valid trigger.

## Adapter boundary

An outbox delivery adapter exposes a small `name` plus `send(payload_json)` protocol. Email, Slack, Teams, webhook, or commercial managed-delivery integrations can implement that boundary without changing policy evaluation or evidence semantics.

Adapters must not modify claim/evidence content in a way that drops provenance. They should preserve `outbox_id` through provider metadata when possible and should be written to tolerate retries.
