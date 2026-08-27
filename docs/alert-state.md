# Alert state, worker leases, and notification delivery

OilSignal separates **policy evaluation**, **notification enqueue**, **worker claim**, and **external delivery**.

A stateless evaluation answers: "Which policies match the current evidence?" A stateful evaluation answers: "Which policies newly transitioned active and should become durable notifications?" Delivery workers then claim those durable notifications with expiring leases before calling an adapter.

## Edge-triggered behavior

Stateful policies persist one row per `policy_id` in local metadata SQLite:

- `active`: whether the policy matched on its last evaluation;
- `last_changed_at`: when it most recently moved between active and inactive;
- `last_triggered_at`: when it most recently created a new notification;
- `last_as_of`: the most recent market observation date involved in the evaluation.

```text
inactive + no match  -> inactive, no notification
inactive + match     -> active,   enqueue once
active   + match     -> active,   suppress duplicate
active   + no match  -> inactive, recovery / re-arm
```

After recovery, a later match enqueues again. A continuously true condition does not become a new alert every time cron runs.

## Transactional outbox

On an inactive-to-active transition, OilSignal writes alert state and a new `AlertOutboxRow` in the **same SQLite transaction**. This closes the lost-alert window where state could become active and the process could crash before a notification existed.

Outbox rows move through these delivery states:

```text
pending -> in_flight -> delivered
                    \-> failed -> in_flight ...
                              \-> dead_letter
```

Rows record the serialized policy evaluation, adapter, attempt count, attempt/delivery timestamps, and latest bounded error.

## Worker-safe claims

A worker must claim a row before calling an external provider. OilSignal uses a short SQLite `BEGIN IMMEDIATE` transaction to:

1. remove expired lease records;
2. find the oldest eligible row that is not actively leased;
3. increment its attempt count;
4. set it `in_flight`;
5. create an `AlertDeliveryLeaseRow` with `worker_id` and expiry;
6. commit before any network call.

The external provider call therefore never holds SQLite's write lock. A second local worker sharing the same metadata database cannot claim the same row while its lease is live.

Attempts are consumed **at claim time**, not after failure. This matters when a process dies after a provider accepts a message: the lease eventually expires and the row can be retried, but crash loops still consume the configured attempt budget.

SQLite does not preserve timezone metadata on round-trip, so alert-storage timestamps are normalized back to UTC-aware values at the storage boundary before lease/backoff comparisons.

## Backoff and dead letters

Failed deliveries use bounded exponential backoff. Defaults are:

- lease: 120 seconds;
- maximum attempts: 5;
- base backoff: 30 seconds;
- maximum backoff: 3600 seconds.

When the attempt budget is exhausted, the notification becomes `dead_letter` and an immutable `AlertDeadLetterRow` snapshot records the payload, reason, attempt count, and dead-letter time.

Operators can inspect active dead letters:

```bash
oilsignal alerts-dead-letters --data-dir ./data
```

Requeue after fixing the underlying problem:

```bash
oilsignal alerts-requeue --outbox-id out_... --data-dir ./data
```

Requeue preserves dead-letter history, marks the dead-letter record as requeued, resets the outbox attempt budget, and returns the notification to `pending`.

## Delivery guarantee

The community outbox is **at least once**, not exactly once.

If a worker dies before provider acceptance, an expired lease allows another worker to retry. If a provider call fails, the row backs off and retries. If a worker dies **after** provider acceptance but **before** local acknowledgement, the message may be delivered again after the lease expires.

Production adapters should use a stable provider idempotency key derived from `outbox_id` whenever supported. No local transaction can make an arbitrary external network call exactly-once.

## CLI

Stateful evaluation atomically enqueues new notifications:

```bash
oilsignal alerts-evaluate --rules examples/alerts.example.json --data-dir ./data
```

Use `--stateless` for a dry run that never mutates alert state:

```bash
oilsignal alerts-evaluate --rules examples/alerts.example.json --data-dir ./data --stateless
```

Drain eligible rows:

```bash
oilsignal alerts-deliver \
  --adapter console \
  --data-dir ./data \
  --worker-id worker-1 \
  --lease-seconds 120 \
  --max-attempts 5 \
  --base-backoff-seconds 30 \
  --max-backoff-seconds 3600
```

Each attempted row returns a receipt containing worker ID, status, attempt count, and timing/error details. Failed, dead-lettered, or lease-lost receipts make the command exit non-zero.

## API

- `POST /api/alerts/evaluate` is stateless and safe for previews.
- `POST /api/alerts/evaluate/stateful` persists edge-trigger state and atomically enqueues newly activated policies.

External delivery stays outside the evaluation request so a slow provider cannot change or roll back a valid market trigger.

## Deployment boundary

The SQLite lease design supports multiple processes on a **single host/shared SQLite database** and is appropriate for the self-hosted community core. It is not presented as a horizontally distributed queue. A future hosted multi-node system should implement the same claim/ack/backoff/dead-letter contract on a server database or queue with stronger distributed coordination.

## Adapter boundary

An adapter exposes `name` plus `send(payload_json)`. Email, Slack, Teams, webhook, or commercial managed-delivery integrations can implement that boundary without changing policy evaluation or evidence semantics.

Adapters must preserve provenance and should propagate `outbox_id` as provider metadata/idempotency whenever possible.
