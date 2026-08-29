# Agent fact products

OilSignal exposes the maintained EIA weekly petroleum registry as a set of small, deterministic agent products in addition to the broader Evidence Pack briefs.

A fact product answers one narrow question:

> What is the latest verified value for this maintained petroleum series, and how did it change from the prior weekly observation?

The output still uses the normal OilSignal Evidence Pack contract, so fact products inherit the existing discovery, product-state polling, semantic ETags, HTTP 402 payment gateway, evidence binding, and paid-fulfillment audit behavior.

## Why facts are separate products

Many autonomous workflows do not need a multi-section weekly brief. A procurement agent may only need refinery utilization, PADD 2 distillate stocks, or crude exports before deciding whether to run another tool.

Fact products make that unit of work explicit:

- one maintained canonical series per SKU;
- latest observation with source URL and raw-source hash;
- deterministic week-over-week calculation when a prior observation exists;
- citations tied to the exact current/prior observations;
- a stable `evidence_sha256` for the fact payload;
- no unrelated petroleum observations in the purchased evidence.

Fact products can be priced independently from broader briefs through `OILSIGNAL_AGENT_SKU_PRICES`, with `OILSIGNAL_AGENT_EVIDENCE_PACK_PRICE_USD` retained as the fallback amount for SKUs without an override. An explicit JSON `null` keeps one SKU unpriced even when the fallback is configured. See [`agent-pricing.md`](agent-pricing.md).

## Discovery

Use the existing catalog:

```http
GET /.well-known/oilsignal-agent.json
GET /api/agent/products
```

Fact entries are machine-identifiable through:

```json
{
  "sku": "fact-us-crude-stocks",
  "product_kind": "fact",
  "series_id": "PET.CRDUUS.W",
  "state_path": "/api/agent/products/fact-us-crude-stocks/state",
  "evidence_path": "/api/agent/products/fact-us-crude-stocks/evidence",
  "quote_path": "/api/agent/products/fact-us-crude-stocks/quote"
}
```

Fact products also advertise the `maintained_series_only` evidence guarantee.

## Maintained fact SKUs

| SKU | Canonical series | Meaning |
|---|---|---|
| `fact-us-crude-stocks` | `PET.CRDUUS.W` | U.S. commercial crude stocks excluding SPR |
| `fact-us-gasoline-stocks` | `PET.GASUS.W` | U.S. total gasoline stocks |
| `fact-us-distillate-stocks` | `PET.DISTUS.W` | U.S. distillate fuel-oil stocks |
| `fact-padd2-distillate-stocks` | `PET.DISTP2.W` | PADD 2 distillate fuel-oil stocks |
| `fact-us-jet-fuel-stocks` | `PET.JETUS.W` | U.S. kerosene-type jet-fuel stocks |
| `fact-us-refinery-utilization` | `PET.UTILUS.W` | U.S. refinery utilization |
| `fact-us-crude-imports` | `PET.CRIMUS.W` | U.S. crude-oil imports |
| `fact-us-crude-production` | `PET.CRPRODUS.W` | U.S. crude-oil field production |
| `fact-us-crude-exports` | `PET.CREXUS.W` | U.S. crude-oil exports |
| `fact-us-crude-refinery-input` | `PET.CRINUS.W` | U.S. refiner net input of crude oil |
| `fact-us-gasoline-product-supplied` | `PET.GASPSUS.W` | U.S. finished motor gasoline product supplied |
| `fact-us-distillate-product-supplied` | `PET.DISTPSUS.W` | U.S. distillate product supplied |
| `fact-us-jet-product-supplied` | `PET.JETPSUS.W` | U.S. jet-fuel product supplied |
| `fact-us-total-products-supplied` | `PET.TOTALPSUS.W` | U.S. petroleum products supplied |

The fact registry is intentionally curated. OilSignal does not automatically turn arbitrary locally ingested series into commercial SKUs. Tests require the fact-series set to stay synchronized with `examples/eia-series.example.json`.

## Evidence shape

A fact is still an `EvidencePack`. For a series with a prior weekly observation, the pack normally contains two numeric claims:

1. the latest observed value;
2. the deterministic week-over-week change.

The evidence observation list is deduplicated, so the current and prior rows appear once each even though the current row supports both claims.

Example structure:

```json
{
  "sku": "fact-us-crude-stocks",
  "report_type": "series_fact",
  "as_of": "2026-08-21",
  "claims": [
    {
      "text": "U.S. commercial crude stocks excluding SPR stood at ...",
      "citations": ["..."],
      "calculation": null
    },
    {
      "text": "Week-over-week change in U.S. commercial crude stocks excluding SPR was ...",
      "citations": ["...", "..."],
      "calculation": {
        "operation": "week_over_week",
        "expression": "current - prior"
      }
    }
  ],
  "observations": ["prior row", "current row"],
  "evidence_sha256": "..."
}
```

The evidence digest changes when the cited observation value, source identity, raw hash, calculation, or claim semantics change. Runtime generation timestamps and commercial price changes do not define semantic evidence identity.

## Product supplied means demand proxy

The four product-supplied fact SKUs preserve the methodology boundary in the purchased claim text itself:

```text
(demand proxy)
```

EIA product supplied should not be represented as a direct measurement of end-use consumption.

## Buyer loop

Fact products use the same agent loop as briefs:

```text
discover
  -> poll /state
  -> 304 when evidence + commercial terms are unchanged
  -> inspect freshness / as_of / price
  -> request /evidence only when the fact is wanted
  -> satisfy 402 when payment enforcement is configured for that SKU
  -> receive evidence + receipt + local fulfillment audit ID
```

A fact whose maintained series is not present in the current local dataset returns `409` before the payment gateway is challenged or verified. OilSignal does not charge for evidence it cannot build.

Price is part of product state, not evidence identity. A price-only change updates `state_sha256` while leaving `evidence_sha256` unchanged, so agents should poll `/state` when commercial changes matter.

## Open-core behavior

When a fact SKU has no resolved price, it is an ordinary self-hosted evidence endpoint even if other SKUs on the same process are paid. Configuring a resolved price without a gateway advertises the price but does not enforce payment, matching the broader Evidence Pack behavior.

This feature does not add a wallet, settlement provider, marketplace, trading recommendation, price prediction, or proprietary petroleum source.
