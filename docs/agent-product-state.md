# Agent Product State

OilSignal exposes a compact product-state resource so machine buyers can decide whether an Evidence Pack is worth fetching before entering the paid fulfillment path.

For every catalog product, discovery now includes:

```text
state_path
quote_path
evidence_path
```

The state resource is:

```text
GET /api/agent/products/<sku>/state
```

It is read-only, does not accept payment credentials, does not call the configured payment gateway, and does not create a paid-fulfillment audit event.

## Response

A successful state response contains compact metadata only:

```json
{
  "schema_version": "1.0",
  "sku": "weekly-petroleum-evidence",
  "title": "Weekly Petroleum Brief",
  "report_type": "weekly_petroleum_brief",
  "as_of": "2026-08-21",
  "evidence_sha256": "...",
  "data_source": "eia:v2",
  "source_fetched_at": "...",
  "freshness": {
    "status": "fresh"
  },
  "fulfillment_available": true,
  "available_for_purchase": true,
  "price": {
    "amount": "0.05",
    "currency": "USD",
    "unit": "evidence_pack",
    "enforcement": "http_402"
  },
  "fulfillment_path": "/api/agent/products/weekly-petroleum-evidence/evidence",
  "payment_enforcement": "http_402",
  "payment_protocols": ["x402-v2"],
  "state_sha256": "..."
}
```

The exact fields in `freshness` follow `DatasetFreshness`; the abbreviated example above shows only the field most buyers normally need first.

The state body intentionally does **not** include report claims, raw observations, payment credentials, provider receipts, or settlement metadata.

## Evidence digest

`evidence_sha256` is produced by the same deterministic Evidence Pack builder used by the fulfillment endpoint. If a buyer later fetches that product before the underlying evidence changes, the fulfilled pack is bound to the same digest.

The digest changes when semantic evidence changes, including cited source hashes or freshness semantics that are part of the Evidence Pack.

## State digest

`state_sha256` fingerprints the buyer-relevant product state:

- evidence digest and report `as_of`
- stable freshness semantics
- data source and source-fetch timestamp
- current fulfillment availability
- price and payment enforcement
- advertised payment protocols

It deliberately excludes volatile `freshness.checked_at`, so polling the same product state does not create a new fingerprint simply because another freshness check ran.

A price or payment-protocol change therefore changes `state_sha256` even if `evidence_sha256` stays the same.

## Conditional polling

State responses use a weak ETag derived from `state_sha256`:

```text
ETag: W/"sha256:<state_sha256>"
Cache-Control: private, max-age=0, must-revalidate
```

A buyer can poll cheaply:

```text
GET /api/agent/products/weekly-petroleum-evidence/state
If-None-Match: W/"sha256:<previous-state-sha>"
```

If neither the evidence nor commercial state changed, OilSignal returns:

```text
304 Not Modified
```

with no body and no payment-gateway interaction.

## Freshness behavior

The Evidence Pack fulfillment endpoint remains fail-closed for stale live WPSR-backed evidence.

The state endpoint is different by design: it can describe the latest locally available product even when freshness is stale. In that case:

```json
{
  "freshness": {"status": "stale"},
  "fulfillment_available": false
}
```

This lets an agent distinguish "the product exists but the source is not current enough to fulfill" from "the product is unknown" without trying a purchase.

Fixture/demo data remains `not_applicable` under the existing freshness policy and is considered fulfillment-available.

## Recommended buyer loop

```text
1. GET /.well-known/oilsignal-agent.json
2. Choose a SKU and its state_path
3. GET state_path, reusing the prior state ETag when available
4. If 304: do nothing
5. If 200 and fulfillment_available=false: do not attempt fulfillment yet
6. If evidence_sha256 is already owned/cached: do not repurchase the same evidence
7. Inspect price/payment_enforcement/payment_protocols
8. Fetch fulfillment_path only when changed evidence is wanted
9. Follow the existing HTTP 402 payment flow when enforcement is active
10. Store the returned evidence ETag/digest for the next comparison
```

The product-state endpoint does not reserve a price, hold inventory, create a payment intent, or guarantee future settlement terms. It reports the server's current state at request time.
