# Founding Pilot Access

OilSignal can onboard its first paying or design-partner customer **before** a third-party payment rail is integrated.

Founding-pilot mode turns an explicit manual commercial agreement into a scoped machine credential. The buyer receives one access key for a deliberate set of priced OilSignal SKUs. Fulfillment still goes through the normal evidence-bound HTTP 402 path and still writes the durable paid-fulfillment audit.

This mode is designed for the first customer, not as a long-term account system.

## What the pilot key means

The pilot key is an **access entitlement**, not cryptographic proof that money settled.

Use it after one of these operator-controlled events:

- a customer signs a pilot agreement;
- an invoice is paid or approved for manual settlement;
- a design partner receives an explicitly authorized trial;
- an agent developer is granted prepaid/test access.

OilSignal continues to record the configured SKU amount/currency in each fulfillment audit so the operator can reconcile usage against the external agreement.

## Recommended first offer

Keep client #1 narrow. A useful starting bundle is:

- `weekly-petroleum-delta` — current WPSR change event;
- `fact-us-crude-stocks` — small single-series inventory fact;
- `fact-padd2-distillate-stocks` — regional downstream-risk fact;
- optionally `weekly-petroleum-evidence` for a human analyst who wants the broader evidence pack.

The exact prices remain operator policy. Per-SKU pricing and the pilot entitlement are separate controls.

## 1. Generate a secret

Generate a random key locally and exchange it with the customer through an appropriate secret-sharing channel:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

The configured key must be at least 24 characters. Never commit it to the repository.

## 2. Configure the offer

Example:

```bash
export OILSIGNAL_AGENT_SKU_PRICES='{
  "weekly-petroleum-delta":"0.02",
  "fact-us-crude-stocks":"0.005",
  "fact-padd2-distillate-stocks":"0.0075"
}'
export OILSIGNAL_AGENT_PRICE_CURRENCY='USD'

export OILSIGNAL_AGENT_PILOT_ACCESS_KEY='<generated-secret>'
export OILSIGNAL_AGENT_PILOT_CUSTOMER='first-client'
export OILSIGNAL_AGENT_PILOT_REFERENCE='invoice-or-deal-001'
export OILSIGNAL_AGENT_PILOT_SKUS='weekly-petroleum-delta,fact-us-crude-stocks,fact-padd2-distillate-stocks'
```

Then restart the configurable server, for example:

```bash
docker compose up --build -d
```

Founding-pilot mode and `OILSIGNAL_AGENT_PAYMENT_GATEWAY_*` remote-gateway mode are mutually exclusive. Startup fails instead of choosing one silently.

## 3. Give the buyer the machine loop

Discovery is public:

```bash
curl https://<host>/.well-known/oilsignal-agent.json
```

The buyer can poll state without spending an entitlement or creating a fulfillment audit:

```bash
curl -i https://<host>/api/agent/products/weekly-petroleum-delta/state
```

A request for changed evidence without the pilot credential returns HTTP 402 and identifies the required header:

```bash
curl -i https://<host>/api/agent/products/weekly-petroleum-delta/evidence
```

Fulfill the granted product:

```bash
curl -i \
  -H 'X-OilSignal-Pilot-Key: <generated-secret>' \
  https://<host>/api/agent/products/weekly-petroleum-delta/evidence
```

A successful response includes the ordinary OilSignal evidence and commerce headers plus:

```text
X-OilSignal-Pilot-Access: granted
X-OilSignal-Payment-Protocol: oilsignal-pilot-v1
X-OilSignal-Payment-Reference: <operator reference>
X-OilSignal-Payment-Payer: pilot:<customer label>
X-OilSignal-Fulfillment-Audit-ID: ful_...
```

The secret key is never written to the fulfillment audit or returned in response bodies/headers.

## 4. Reconcile the client

Every served priced pilot fulfillment is appended to the same local audit used by payment-gateway fulfillment:

```bash
oilsignal commerce-audit --sku weekly-petroleum-delta --data-dir ./data
oilsignal commerce-audit --gateway-reference invoice-or-deal-001 --data-dir ./data
```

The event contains the non-secret customer/payer label, operator reference, SKU, exact amount/currency, evidence digest, and fulfillment timestamp.

The fulfillment audit is not an accounts-receivable or settlement ledger. Reconcile it against the invoice, CRM deal, contract, or external payment record represented by `OILSIGNAL_AGENT_PILOT_REFERENCE`.

## Scope and security

- Only exact SKUs in `OILSIGNAL_AGENT_PILOT_SKUS` are authorized.
- Unknown or duplicate SKU configuration fails startup.
- Pilot and remote payment gateway modes cannot both be enabled.
- Key comparison is constant-time.
- Customer/reference metadata rejects response-header injection characters.
- The key is environment-only and is never persisted in OilSignal metadata.
- Changing/removing the environment key revokes the current pilot credential after restart.
- There is deliberately one pilot credential per process in this first-client implementation.
- There are no built-in quotas, expiry dates, customer database, subscription billing, tax, invoicing, or account recovery.

Move to a real remote payment/account gateway when multiple independent customers, automated settlement, per-customer quotas, key rotation without restart, or account lifecycle management becomes necessary.

## Success criterion for client #1

A founding pilot is successful when a real external user can repeatedly complete this loop without operator intervention:

```text
discover -> poll state -> detect changed evidence -> fulfill granted SKU -> verify digest -> reconcile audit ID
```

For a human client, the same evidence can be consumed through the broader weekly product or rendered reporting surfaces. For an agent client, the state/ETag loop is the preferred integration because unchanged polling remains free and side-effect-free.
