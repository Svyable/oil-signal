# Agent Evidence Products

OilSignal exposes deterministic petroleum intelligence as machine-purchasable **Evidence Packs** instead of forcing another agent to scrape a dashboard or reverse-engineer narrative prose.

The community core owns the product contract: SKU, price metadata, freshness, evidence construction, semantic digest, and an optional HTTP 402 orchestration boundary. A deployed payment adapter owns its payment protocol, credential verification, settlement, replay protection, and protocol-specific headers.

No real payment provider is bundled or silently enabled. Setting a price by itself does not make the endpoint paid.

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

With a price but no payment gateway, OilSignal reports a price while keeping enforcement external. This is intentional: the core never claims that money is being verified when no verifier exists.

With both a price and an injected `PaymentGateway`, the same quote reports:

```json
{
  "sku": "weekly-petroleum-evidence",
  "available_for_purchase": true,
  "price": {
    "amount": "0.05",
    "currency": "USD",
    "unit": "evidence_pack",
    "enforcement": "http_402"
  },
  "fulfillment_path": "/api/agent/products/weekly-petroleum-evidence/evidence",
  "payment_enforcement": "http_402",
  "payment_protocols": ["<adapter protocol>"]
}
```

The current pricing setting applies one unit price to all Evidence Pack SKUs. A hosted commercial layer can provide SKU-specific pricing later without changing the pack schema.

## Fulfillment ordering

A paid request follows this order:

1. load the current dataset and ingestion provenance;
2. apply the release-aware freshness gate;
3. construct the requested Evidence Pack;
4. calculate its semantic `evidence_sha256`;
5. honor a matching `If-None-Match` with a free `304 Not Modified`;
6. if semantic evidence changed, build an evidence-bound payment requirement;
7. ask the configured gateway to verify the request headers;
8. on rejection, return a protocol-specific 402 challenge plus an OilSignal problem body;
9. on successful verification, verify the receipt binding and return the Evidence Pack.

Evidence validity therefore comes **before commerce**. OilSignal does not charge for a SKU that the current dataset cannot build or for live evidence that fails freshness checks.

## Evidence-bound payment requirement

For changed evidence, OilSignal constructs a `PaymentRequirement` containing:

- SKU;
- amount and currency;
- fulfillment resource path;
- semantic `evidence_sha256`;
- product description;
- stable external operation ID.

The operation ID is deterministic for the exact purchased evidence:

```text
oilsignal:<sku>:sha256:<evidence_sha256>
```

The payment adapter receives that same requirement for both challenge generation and verification. On success it must echo the exact operation ID in `VerifiedPayment.external_id`.

OilSignal fails with `502 Bad Gateway` rather than serving the pack if the adapter returns:

- a different protocol than configured; or
- an `external_id` for different evidence.

That makes evidence/receipt binding executable rather than advisory.

## HTTP 402 response

A rejected or missing credential returns `402 Payment Required` with media type `application/problem+json`.

The machine-readable body includes commercial identity only:

```json
{
  "type": "urn:oilsignal:payment-required",
  "title": "Payment Required",
  "status": 402,
  "detail": "payment credential is required",
  "sku": "weekly-petroleum-evidence",
  "amount": "0.05",
  "currency": "USD",
  "evidence_sha256": "...",
  "external_id": "oilsignal:weekly-petroleum-evidence:sha256:...",
  "resource_path": "/api/agent/products/weekly-petroleum-evidence/evidence",
  "payment_protocol": "<adapter protocol>",
  "challenge_id": "..."
}
```

The 402 body never contains purchased claims or source observations.

OilSignal adds:

```text
Cache-Control: no-store
X-OilSignal-Evidence-SHA256: <digest>
X-OilSignal-SKU: <sku>
X-OilSignal-Payment-Protocol: <adapter protocol>
X-OilSignal-Payment-External-ID: <external id>
```

The adapter adds its own challenge headers. OilSignal does not assume their names.

## Protocol-neutral gateway boundary

`PaymentGateway` is deliberately header-neutral. An adapter declares:

```text
protocol: str
credential_headers: tuple[str, ...]
challenge(requirement) -> PaymentChallenge
verify(request_headers, requirement) -> VerifiedPayment
```

`PaymentChallenge.response_headers` contains the protocol's 402 challenge headers. `VerifiedPayment.response_headers` contains its successful receipt/settlement response headers.

This permits different protocol shapes without teaching the intelligence core how to parse them. Tests cover both:

- an MPP-shaped adapter using `WWW-Authenticate`, `Authorization`, and `Payment-Receipt`;
- an x402-v2-shaped adapter using `PAYMENT-REQUIRED`, `PAYMENT-SIGNATURE`, and `PAYMENT-RESPONSE`.

Those are compatibility-shape tests, not bundled production adapters or claims that OilSignal itself performs MPP/x402 settlement.

Payment adapters are responsible for:

- validating credentials/signatures;
- actual settlement or credit consumption;
- replay protection/idempotency;
- protocol-specific challenge construction;
- protocol-specific success receipts;
- provider/network error handling;
- keeping payment secrets outside response payloads.

See [`payment-gateways.md`](payment-gateways.md) for the adapter contract and security checklist.

## Header integrity

Adapters may return protocol-owned headers, but OilSignal reserves its own evidence/cache boundary. An adapter cannot override headers such as:

- `ETag`;
- `Cache-Control`;
- `Vary`;
- content headers;
- `X-OilSignal-Evidence-SHA256`;
- `X-OilSignal-SKU`;
- OilSignal payment-binding headers.

A collision fails closed with `502 Bad Gateway`.

The gateway's declared credential headers become `Vary` so intermediaries do not treat differently authorized requests as the same representation.

## What `evidence_sha256` commits to

`evidence_sha256` is a SHA-256 digest over the semantic purchased evidence:

- schema version and SKU;
- report type/title/as-of date;
- data source identity;
- semantic freshness state;
- normalized claims and citations;
- deterministic calculation semantics;
- cited observation values, units, source URLs, and raw-source hashes.

It intentionally excludes runtime-only fields such as pack `generated_at`, source fetch timestamp, and random internal report/claim/calculation IDs. An agent can therefore fetch equivalent evidence twice and receive the same digest even though OilSignal created fresh model objects.

If a cited observation's `raw_hash` changes, the evidence digest changes.

This digest is an integrity/fingerprinting primitive, not a seller signature. A production payment adapter can cryptographically bind its own receipt to the OilSignal external ID/digest.

## Poll free, pay for changed intelligence

OilSignal returns:

```text
ETag: W/"sha256:<evidence_sha256>"
X-OilSignal-Evidence-SHA256: <evidence_sha256>
X-OilSignal-SKU: <sku>
Cache-Control: private, max-age=0, must-revalidate
```

A buyer can revalidate with:

```text
If-None-Match: W/"sha256:<previous evidence_sha256>"
```

If semantic evidence is unchanged, OilSignal returns `304 Not Modified` with an empty body **before calling the payment gateway**. This is a deliberate product rule: agents can cheaply poll for new petroleum intelligence and pay only when there is a changed pack to receive.

For GET revalidation OilSignal uses weak comparison semantics, so the equivalent quoted tag without the `W/` prefix is also accepted.

## Failure semantics

| Status | Meaning |
| --- | --- |
| `304` | semantic evidence unchanged; no payment verification performed |
| `402` | changed evidence is available, but payment is missing/rejected |
| `409` | evidence cannot currently be constructed from the dataset |
| `502` | payment adapter returned internally inconsistent/prohibited data |
| `503` | payment adapter is unavailable |

The ordinary live-data freshness policy remains upstream of these commerce states.

## Why agents would pay instead of reading raw public data

The product is not a resale of a public EIA row. The commercial unit is the **verified transformation** around source data:

- route maintenance and source-contract verification;
- release-aware stale-data protection;
- deterministic analytics;
- claim-level citations;
- calculation lineage;
- source hashes;
- stable semantic fingerprints;
- evidence-bound payment identity;
- machine discovery and OpenAPI schemas;
- cache-efficient, free unchanged-data revalidation.

That makes the output useful as a trusted input to another agent's procurement, risk, planning, research, or reporting workflow while preserving the original public-source attribution.
