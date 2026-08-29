# Agent SKU pricing

OilSignal can price agent products individually without changing evidence identity or introducing a billing database.

The pricing model is intentionally small and deterministic:

1. an exact SKU override wins when present;
2. otherwise `OILSIGNAL_AGENT_EVIDENCE_PACK_PRICE_USD` is the fallback amount;
3. when neither produces an amount, the SKU is unpriced.

All configured products currently share `OILSIGNAL_AGENT_PRICE_CURRENCY`.

## Configuration

Set a fallback amount when most products should share one price:

```bash
export OILSIGNAL_AGENT_EVIDENCE_PACK_PRICE_USD='0.05'
```

Then override individual products with a JSON object:

```bash
export OILSIGNAL_AGENT_SKU_PRICES='{
  "fact-us-crude-stocks": "0.005",
  "fact-padd2-distillate-stocks": "0.0075",
  "crude-balance-evidence": "0.10",
  "refinery-utilization-evidence": null
}'
```

The example resolves to:

| SKU | Resolved amount |
|---|---:|
| `fact-us-crude-stocks` | `0.005` |
| `fact-padd2-distillate-stocks` | `0.0075` |
| `crude-balance-evidence` | `0.10` |
| `refinery-utilization-evidence` | unpriced |
| any SKU without an override | `0.05` fallback |

A JSON `null` is an explicit unpriced override. It is different from omitting the key, which uses the fallback.

Use `null` rather than zero when a SKU should stay outside the payment gate. Zero is still a configured amount and may be sent through a configured payment adapter.

## Fail-closed configuration

OilSignal rejects unknown SKU keys during app construction.

For example, this is a configuration error rather than a silent fallback:

```json
{
  "fact-us-crdue-stocks": "0.005"
}
```

This prevents a typo from accidentally charging the fallback amount for a product an operator intended to price differently.

Negative amounts are also rejected.

## One resolver, all buyer surfaces

The same resolved amount is used for:

- `/.well-known/oilsignal-agent.json` discovery;
- `/api/agent/products/{sku}/quote`;
- `/api/agent/products/{sku}/state`;
- the HTTP 402 `PaymentRequirement`;
- the durable paid-fulfillment audit.

A configured payment gateway only gates a SKU when that SKU has a resolved amount. An explicitly unpriced SKU remains open even if other products on the same OilSignal process use HTTP 402.

This is an important invariant: OilSignal must not advertise one amount and verify or audit another.

## State identity versus evidence identity

Price is commercial state, not evidence.

Changing only a SKU price therefore:

- does **not** change `evidence_sha256`;
- **does** change `state_sha256`;
- changes the `/state` ETag;
- changes the payment operation ID.

Agents that care about both data and price should poll `/state`.

The `/evidence` ETag remains evidence-only. If petroleum evidence is unchanged, the evidence endpoint can still return `304 Not Modified` before payment verification even when a price was changed separately. The state endpoint is the authoritative cheap polling surface for commercial changes.

## Payment operation identity

Payment requirements are bound to SKU, normalized currency/amount, and the exact evidence digest.

The operation ID shape is:

```text
oilsignal:<sku>:<CURRENCY>:<amount>:sha256:<evidence_sha256>
```

For example:

```text
oilsignal:fact-us-crude-stocks:USD:0.005:sha256:<digest>
```

Equivalent decimal representations normalize to the same identity, so `0.0050` and `0.005` are the same commercial term.

A real price change creates a new operation ID even when the evidence digest is unchanged. This prevents a gateway or downstream idempotency store keyed by `external_id` from confusing a previous settlement with a newly priced requirement.

The evidence digest remains the final component so buyers can still see which exact evidence version the operation authorizes.

## Fulfillment audit

Paid fulfillment audit rows record the resolved amount and currency used by the verified requirement.

A fact priced at `0.005` therefore produces a fulfillment event with `amount=0.005`; a broader brief using the `0.05` fallback produces a separate requirement and audit amount.

Unpriced fulfillments do not create paid-fulfillment audit rows because no paid fulfillment occurred.

## Security and operating boundary

SKU pricing configuration is not a credential. Payment-gateway secrets remain in their existing secret settings and are never placed in the pricing map.

This community pricing policy is static process configuration. It does not implement:

- customer-specific pricing;
- promotional codes;
- subscriptions or quotas;
- tax calculation;
- invoicing;
- dynamic market-based pricing;
- settlement or ledger accounting.

Those concerns can live in a hosted control plane later while preserving the same product-state and payment-requirement contracts.
