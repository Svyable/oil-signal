# Agent Evidence Products

OilSignal can expose deterministic petroleum intelligence as machine-purchasable **Evidence Packs** instead of forcing an agent to scrape a dashboard or reverse-engineer a narrative report.

The community core defines the product and fulfillment contract. Payment enforcement is intentionally external so a hosted deployment can wrap the same endpoint with HTTP 402, x402, MPP, an API gateway, credits, or another commercial rail without changing the evidence semantics.

## Product catalog

Agents can discover the service at:

```text
GET /.well-known/oilsignal-agent.json
GET /api/agent/products
```

The catalog also points to FastAPI's ordinary OpenAPI document at `/openapi.json`.

Current SKUs:

| SKU | Purpose |
| --- | --- |
| `weekly-petroleum-evidence` | broad weekly U.S. petroleum fundamentals |
| `distillate-risk-evidence` | PADD 2 distillate inventory plus U.S. distillate product supplied |
| `refinery-utilization-evidence` | U.S. refinery utilization and deterministic change calculations |
| `crude-balance-evidence` | partial U.S. crude-flow and commercial-stock reconciliation |

Every product advertises the same evidence guarantees:

- freshness is checked before fulfillment;
- every numerical market claim is cited;
- derived claims include a deterministic calculation trace;
- cited observations include the ingestion `raw_hash`;
- equivalent evidence produces the same `evidence_sha256` even if internal report/claim UUIDs are regenerated.

## Quotes and pricing

Configure an advertised per-pack price:

```bash
export OILSIGNAL_AGENT_EVIDENCE_PACK_PRICE_USD='0.05'
export OILSIGNAL_AGENT_PRICE_CURRENCY='USD'
```

Then query a SKU:

```text
GET /api/agent/products/weekly-petroleum-evidence/quote
```

A configured quote reports:

```json
{
  "sku": "weekly-petroleum-evidence",
  "available_for_purchase": true,
  "price": {
    "amount": "0.05",
    "currency": "USD",
    "unit": "evidence_pack",
    "enforcement": "external"
  },
  "fulfillment_path": "/api/agent/products/weekly-petroleum-evidence/evidence",
  "payment_enforcement": "external",
  "payment_protocols": []
}
```

If no price is configured, OilSignal explicitly reports `available_for_purchase: false`, `price: null`, and `payment_enforcement: not_configured`. The community core never pretends a payment rail is active when it is not.

The current pricing setting applies one unit price to all Evidence Pack SKUs. A hosted commercial layer can provide SKU-specific pricing without changing the pack schema.

## Fulfillment

Retrieve a pack:

```text
GET /api/agent/products/weekly-petroleum-evidence/evidence
```

The response contains:

- product SKU and schema version;
- report type/title/as-of date;
- live-data provenance and source fetch time;
- release-aware freshness status;
- stable claim fingerprints;
- stable calculation fingerprints;
- cited source observations and their raw ingestion hashes;
- a top-level `evidence_sha256`.

The endpoint fails closed under the same live-WPSR freshness policy as OilSignal's ordinary reports and Q&A.

## What `evidence_sha256` commits to

`evidence_sha256` is a SHA-256 digest over the semantic purchased evidence:

- schema version and SKU;
- report type/title/as-of date;
- data source identity;
- semantic freshness state (status, latest observation, expected week-ending, stale series, live-series count);
- normalized claims and citations;
- deterministic calculation semantics;
- cited observation values, units, source URLs, and raw-source hashes.

It intentionally excludes runtime-only fields such as pack `generated_at`, source fetch timestamp, and random internal report/claim/calculation IDs. That means an agent can fetch the same underlying evidence twice and receive the same digest even though OilSignal constructed fresh internal model objects.

If a cited observation's `raw_hash` changes, the evidence digest changes.

This digest is an integrity/fingerprinting primitive, not a digital signature. A hosted product that needs cryptographic seller identity should sign the digest or bind it into the payment receipt at the commerce layer.

## Cache and repurchase semantics

OilSignal returns:

```text
ETag: W/"sha256:<evidence_sha256>"
X-OilSignal-Evidence-SHA256: <evidence_sha256>
X-OilSignal-SKU: <sku>
Cache-Control: private, max-age=0, must-revalidate
```

The ETag is deliberately **weak** because the JSON representation includes runtime fields such as `generated_at` and freshness `checked_at` that can change while the purchased semantic evidence remains equivalent. `X-OilSignal-Evidence-SHA256` is the stable semantic integrity fingerprint.

An agent can revalidate without downloading the full pack:

```text
If-None-Match: W/"sha256:<previous evidence_sha256>"
```

For GET revalidation OilSignal uses weak comparison semantics, so the equivalent quoted tag without the `W/` prefix is also accepted. If the semantic evidence is unchanged, OilSignal returns `304 Not Modified` with an empty body.

A future payment middleware should decide whether a 304 revalidation is free, discounted, or billable. That commercial decision is deliberately not encoded into the intelligence core.

## Payment-layer boundary

The fulfillment endpoint is designed to sit behind a payment gateway:

```text
agent
  -> GET evidence endpoint
  -> payment middleware / gateway
  -> OilSignal freshness + report builder
  -> Evidence Pack
```

A 402-based deployment can therefore use this pattern:

1. agent discovers the SKU and quote;
2. agent requests the fulfillment endpoint;
3. an external payment layer returns `402 Payment Required` when no valid payment credential is present;
4. the agent pays and retries;
5. the payment layer verifies the credential;
6. OilSignal builds the fresh deterministic Evidence Pack;
7. the payment layer can bind its receipt to the returned `evidence_sha256`.

OilSignal does not currently advertise a payment protocol because none is implemented in the community core. This prevents false claims of x402, MPP, card, stablecoin, or other payment support.

## Why agents would pay for this instead of raw public data

The product is not a resale of a public EIA row. The commercial unit is the **verified transformation** around the source data:

- route maintenance and source-contract verification;
- release-aware stale-data protection;
- deterministic analytics;
- claim-level citations;
- calculation lineage;
- source hashes;
- stable semantic fingerprints;
- machine discovery and OpenAPI schemas;
- cache-efficient conditional fulfillment.

That makes the output useful as a trusted input to another agent's procurement, risk, planning, research, or reporting workflow while preserving the original public-source attribution.
