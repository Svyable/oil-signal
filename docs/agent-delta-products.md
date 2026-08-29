# Agent delta products

OilSignal exposes `weekly-petroleum-delta` as a compact machine product for agents that care about **what changed in the current weekly petroleum event** rather than the full level-oriented Weekly Petroleum Evidence Pack.

The delta product uses the same deterministic Evidence Pack contract as every other agent product, so it inherits discovery, product-state polling, semantic ETags, freshness checks, HTTP 402 orchestration, payment receipt binding, raw-source hashes, and local paid-fulfillment audit.

## Product contract

Discover the product through the existing catalog:

```http
GET /.well-known/oilsignal-agent.json
GET /api/agent/products
```

The catalog entry is machine-identifiable:

```json
{
  "sku": "weekly-petroleum-delta",
  "product_kind": "delta",
  "state_path": "/api/agent/products/weekly-petroleum-delta/state",
  "evidence_path": "/api/agent/products/weekly-petroleum-delta/evidence",
  "quote_path": "/api/agent/products/weekly-petroleum-delta/quote"
}
```

It advertises two additional evidence guarantees:

```text
current_event_week_only
week_over_week_changes_only
```

## What the delta contains

For each maintained weekly petroleum series that has both:

1. a new observation on the product's current `as_of` week; and
2. a prior observation available for comparison,

OilSignal emits one numeric change claim backed by the existing deterministic `week_over_week` calculation.

A claim looks conceptually like:

```text
U.S. crude oil stocks increased by 1,500.0 thousand barrels
from 2026-08-14 to 2026-08-21.
```

Each claim cites exactly the prior and current observations. The resulting Evidence Pack therefore carries the raw-source hashes for both inputs and a calculation fingerprint bound to the exact dates, values, operation, expression, and unit.

The delta does **not** repeat a separate current-level claim. Agents that need the absolute level as a product should use the broader Weekly Petroleum Evidence Pack or the corresponding single-series Fact SKU.

Product-supplied metrics keep `(demand proxy)` in the purchased delta claim text. EIA product supplied is not represented as a direct measurement of end-use consumption.

## Current event week only

The delta report uses the maximum available observation date as its event `as_of` date. A maintained series is included only when its latest usable observation is on that same date.

If another series is lagging on an older week, OilSignal omits that old change rather than replaying it as if it belonged to the current event. This is intentionally stricter than simply taking the last two rows of every series in storage.

If no maintained series has a current-week prior/current pair, delta construction fails instead of inventing an empty or stale event.

## Buyer loop

The preferred agent loop is:

```text
discover weekly-petroleum-delta
  -> poll /state
  -> 304 while the semantic event + commercial state are unchanged
  -> inspect freshness / as_of / price
  -> request /evidence only when the new event is wanted
  -> satisfy 402 when payment enforcement is configured
  -> receive cited delta evidence + receipt + fulfillment audit ID
```

The delta's `evidence_sha256` is stable for semantically equivalent evidence. Runtime generation timestamps do not change it. A new weekly observation, revised cited value/raw hash, changed claim semantics, or changed calculation input changes the digest.

## Why this is not an arbitrary historical diff API

This first delta product is deliberately stateless. OilSignal does not keep per-buyer cursors, purchase history, or arbitrary historical Evidence Pack snapshots just to answer a hash supplied by a client.

A client-provided digest alone is insufficient to prove which historical source state it represented if that state was never retained. Pretending otherwise would weaken the evidence contract.

Instead, `weekly-petroleum-delta` represents the deterministic **current weekly change event**. Buyers use `/state` and its semantic ETag as their cursor. A future hosted event service can add durable historical event retention or subscriber cursors without changing the evidence calculation semantics defined here.

## Commerce behavior

On the community runtime, the delta product uses the same configured agent Evidence Pack price as other products. A configured payment gateway therefore gates the delta through the existing evidence-bound 402 path without adding another payment rail.

The paid path still builds and freshness-checks the delta before payment is challenged. If the delta cannot be constructed from current evidence, OilSignal fails before any payment side effect.

The local fulfillment audit records the delta SKU, resource path, evidence digest, amount/currency, payment protocol, and provider reconciliation metadata exactly like other paid products.

## Product positioning

Use:

- `weekly-petroleum-delta` when an agent wants the current cross-market weekly changes only;
- a `fact-*` SKU when an agent wants one maintained series with its latest level and week-over-week change;
- `weekly-petroleum-evidence` when an agent wants the broader weekly level-oriented snapshot;
- specialized evidence SKUs when the workflow needs a focused multi-series interpretation such as distillate risk or crude-balance reconciliation.

This product remains decision-support evidence. It does not predict prices, recommend trades, size positions, or execute orders.
