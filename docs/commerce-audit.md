# Paid Fulfillment Audit

OilSignal keeps an append-only local audit event for every paid Evidence Pack that it actually serves.

This is a **fulfillment audit**, not a billing ledger. It records what OilSignal released after a payment gateway verified the evidence-bound requirement. The payment service remains the source of truth for settlement, refunds, charge state, and rail-specific replay/idempotency semantics.

## Fulfillment invariant

The paid response path is ordered as:

1. build and freshness-check the Evidence Pack;
2. honor unchanged `If-None-Match` with a free 304;
3. verify the payment requirement;
4. reject protocol or `external_id` mismatches;
5. reject payment headers that collide with OilSignal's reserved response boundary;
6. commit the fulfillment audit row;
7. return the purchased Evidence Pack.

If the audit row cannot be committed, OilSignal returns 503 and does not serve the purchased claims. The payment service therefore needs the idempotent retry behavior already required by the gateway contract because a provider may have accepted payment immediately before a local persistence failure or process crash.

## Stored fields

Each event stores only reconciliation metadata:

```text
id
fulfilled_at
external_id
sku
evidence_sha256
amount
currency
resource_path
protocol
gateway_reference
payer
```

`external_id` remains the evidence-bound commercial identity:

```text
oilsignal:<sku>:sha256:<evidence_sha256>
```

`gateway_reference` is the optional non-secret reference returned by the configured payment service. `payer` is stored only when the adapter deliberately returns a non-secret payer identifier.

OilSignal does **not** store:

- buyer credential headers;
- `Authorization` or payment signatures;
- gateway bearer tokens;
- protocol receipt headers;
- private keys or wallet material;
- provider response bodies.

## Append-only semantics

`external_id` is not a unique purchase ID. Multiple agents can buy the same evidence digest, and the same buyer can legitimately receive the same evidence more than once under a payment rail's own rules.

For that reason every successful fulfillment gets a distinct `ful_...` audit event ID. Do not calculate revenue by counting these rows. Reconcile them against the payment provider using `external_id` plus `gateway_reference` and the provider's own settlement records.

## Buyer-visible audit ID

A successful paid response includes:

```text
X-OilSignal-Fulfillment-Audit-ID: ful_...
```

This identifier is safe to use in support tickets and reconciliation workflows. Payment adapters cannot override it because it is part of OilSignal's reserved response-header boundary.

## Operator CLI

List the newest events:

```bash
oilsignal commerce-audit --data-dir ./data
```

Filter by the exact evidence-bound operation:

```bash
oilsignal commerce-audit \
  --data-dir ./data \
  --external-id 'oilsignal:weekly-petroleum-evidence:sha256:<digest>'
```

Reconcile a provider reference:

```bash
oilsignal commerce-audit \
  --data-dir ./data \
  --gateway-reference 'settlement-123'
```

Filter a SKU:

```bash
oilsignal commerce-audit \
  --data-dir ./data \
  --sku weekly-petroleum-evidence \
  --limit 50
```

The audit is intentionally CLI-only in the MVP. OilSignal does not expose an unauthenticated HTTP endpoint containing payer/reference metadata.

## SQLite deployment boundary

The audit uses the same local metadata SQLite database as ingestion and alert state. A new table is created automatically; existing installations do not require an in-place column migration.

This is appropriate for the self-hosted/local MVP. A horizontally distributed hosted service should move fulfillment audit persistence to the same durable server-side database boundary used for other hosted state rather than treating independent SQLite files as a shared ledger.
