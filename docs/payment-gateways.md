# Payment Gateway Adapters

OilSignal's paid Evidence Pack path is intentionally split into two responsibilities:

- **OilSignal core** defines the product, price, evidence digest, freshness policy, HTTP 402 orchestration, receipt/evidence binding checks, and local paid-fulfillment audit.
- A **payment service** implements the actual machine-payment protocol, credential verification, settlement/credit consumption, replay protection, and protocol-specific HTTP headers.

The repository does not ship a fake settlement provider. It does ship a small HTTP bridge so a hosted operator can connect a real verifier/settlement service without writing Python inside OilSignal.

## Built-in HTTP bridge

The runtime entrypoint `oilsignal.api.server:app` constructs `HttpPaymentGateway` when the gateway environment is configured. The ordinary self-hosted defaults remain open and ungated because the bridge is disabled when no gateway URL/protocol is set.

Minimum production configuration:

```bash
export OILSIGNAL_AGENT_EVIDENCE_PACK_PRICE_USD='0.05'
export OILSIGNAL_AGENT_PRICE_CURRENCY='USD'
export OILSIGNAL_AGENT_PAYMENT_GATEWAY_URL='https://payments.example.com/oilsignal'
export OILSIGNAL_AGENT_PAYMENT_GATEWAY_PROTOCOL='x402-v2'
export OILSIGNAL_AGENT_PAYMENT_GATEWAY_CREDENTIAL_HEADERS='PAYMENT-SIGNATURE'
export OILSIGNAL_AGENT_PAYMENT_GATEWAY_BEARER_TOKEN='operator-to-gateway-secret'
```

Then run:

```bash
uvicorn oilsignal.api.server:app --host 0.0.0.0 --port 8000
```

`docker compose up --build` uses the same configurable server entrypoint and passes the payment environment through to the API container.

The bridge uses HTTPS by default, a five-second timeout, and never follows redirects. Plain HTTP is rejected unless `OILSIGNAL_AGENT_PAYMENT_GATEWAY_ALLOW_INSECURE_HTTP=true` is explicitly set for an intentionally insecure local/private deployment.

## Remote HTTP contract

The configured URL is a base URL. The payment service implements two POST endpoints:

```text
POST <gateway-url>/challenge
POST <gateway-url>/verify
```

OilSignal sends:

```text
X-OilSignal-Gateway-Contract: oilsignal.payment-gateway.v1
Content-Type: application/json
```

If `OILSIGNAL_AGENT_PAYMENT_GATEWAY_BEARER_TOKEN` is configured, OilSignal authenticates to the remote service with:

```text
Authorization: Bearer <operator secret>
```

That operator credential is never copied into buyer-facing headers or bodies.

### Challenge request

```json
{
  "contract_version": "oilsignal.payment-gateway.v1",
  "requirement": {
    "sku": "weekly-petroleum-evidence",
    "amount": "0.05",
    "currency": "USD",
    "resource_path": "/api/agent/products/weekly-petroleum-evidence/evidence",
    "evidence_sha256": "...",
    "external_id": "oilsignal:weekly-petroleum-evidence:sha256:...",
    "description": "Weekly Petroleum Brief"
  }
}
```

A successful challenge response is:

```json
{
  "protocol": "x402-v2",
  "challenge_id": "optional-provider-id",
  "response_headers": {
    "PAYMENT-REQUIRED": "protocol-owned-value"
  }
}
```

The remote service should return 2xx only when it produced a valid challenge. Other status codes are treated as payment infrastructure failure and OilSignal returns 503 rather than pretending the buyer was at fault.

### Verify request

OilSignal forwards **only** the buyer header names listed in `OILSIGNAL_AGENT_PAYMENT_GATEWAY_CREDENTIAL_HEADERS`. Cookies and unrelated request headers are never sent to the payment service.

Example:

```json
{
  "contract_version": "oilsignal.payment-gateway.v1",
  "requirement": {
    "sku": "weekly-petroleum-evidence",
    "amount": "0.05",
    "currency": "USD",
    "resource_path": "/api/agent/products/weekly-petroleum-evidence/evidence",
    "evidence_sha256": "...",
    "external_id": "oilsignal:weekly-petroleum-evidence:sha256:...",
    "description": "Weekly Petroleum Brief"
  },
  "credentials": {
    "PAYMENT-SIGNATURE": "buyer-provided-credential"
  }
}
```

A successful verification response is:

```json
{
  "protocol": "x402-v2",
  "external_id": "oilsignal:weekly-petroleum-evidence:sha256:...",
  "reference": "optional-settlement-reference",
  "payer": "optional-non-secret-payer-id",
  "response_headers": {
    "PAYMENT-RESPONSE": "protocol-owned-receipt"
  }
}
```

The returned `external_id` must exactly match the requirement. OilSignal rejects mismatches with 502 before serving the Evidence Pack.

A `/verify` response with HTTP 402 is treated as buyer rejection and becomes a fresh OilSignal 402 challenge. Other non-2xx responses become 503. Remote response bodies are not copied into buyer-facing errors, preventing provider diagnostics or secrets from leaking through OilSignal.

## Adapter interface

The bridge implements the same protocol available to custom in-process integrations in `oilsignal.agent.commerce.PaymentGateway`:

```python
class PaymentGateway(Protocol):
    protocol: str
    credential_headers: tuple[str, ...]

    def challenge(self, requirement: PaymentRequirement) -> PaymentChallenge: ...

    def verify(
        self,
        request_headers: Mapping[str, str],
        requirement: PaymentRequirement,
    ) -> VerifiedPayment: ...
```

`protocol` is advertised through the OilSignal product quote when HTTP 402 enforcement is active.

`credential_headers` lists request headers that can change authorization state. OilSignal emits them in `Vary`. The built-in HTTP bridge validates the names, rejects duplicates, caps the list at eight, and refuses generic browser/routing headers such as `Cookie`, `Host`, and `Content-Length`.

## PaymentRequirement

Every changed Evidence Pack creates a requirement containing:

```text
sku
amount
currency
resource_path
evidence_sha256
external_id
description
```

The external operation identity is:

```text
oilsignal:<sku>:sha256:<evidence_sha256>
```

The payment service should include this value, or an unambiguous cryptographic commitment to it, in provider-side payment intent/authorization metadata whenever the underlying rail permits it.

The same requirement is supplied to challenge and verification.

## Protocol-owned headers

Payment protocols can use their normal HTTP header shapes. The bridge does not hard-code MPP or x402 semantics.

Examples already covered by OilSignal's API contract tests include:

```text
MPP-shaped challenge: WWW-Authenticate: Payment ...
MPP-shaped success:   Payment-Receipt: ...

x402-v2-shaped challenge: PAYMENT-REQUIRED: ...
x402-v2-shaped request:   PAYMENT-SIGNATURE: ...
x402-v2-shaped success:   PAYMENT-RESPONSE: ...
```

These are header-shape compatibility examples, not claims that OilSignal performs those protocols' settlement itself.

OilSignal additionally emits vendor-neutral binding and reconciliation metadata after successful verification and audit commit:

```text
X-OilSignal-Payment-Protocol: <protocol>
X-OilSignal-Payment-External-ID: oilsignal:<sku>:sha256:<digest>
X-OilSignal-Payment-Reference: <optional reference>
X-OilSignal-Payment-Payer: <optional payer>
X-OilSignal-Fulfillment-Audit-ID: ful_...
```

Do not put secrets, raw payment credentials, private keys, or bearer tokens into these metadata fields.

## Reserved response headers

OilSignal rejects gateway response headers that attempt to override the evidence/representation boundary, including:

```text
Cache-Control
Content-Length
Content-Type
ETag
Vary
X-OilSignal-Evidence-SHA256
X-OilSignal-SKU
X-OilSignal-Payment-Protocol
X-OilSignal-Payment-Reference
X-OilSignal-Payment-Payer
X-OilSignal-Payment-External-ID
X-OilSignal-Fulfillment-Audit-ID
```

The HTTP bridge also rejects malformed header names, CR/LF in values, excessively long values, and excessive header counts before those headers reach FastAPI.

## Durable fulfillment audit

Every paid Evidence Pack that OilSignal actually serves gets an append-only local fulfillment event. The paid path is deliberately ordered as:

```text
build/freshness-check evidence
-> free unchanged 304 check
-> payment verification
-> protocol/external-id binding checks
-> reserved-header checks
-> commit fulfillment audit
-> serve purchased Evidence Pack
```

If audit storage cannot commit, OilSignal returns 503 and does not serve the purchased claims. This makes “paid response served” and “local fulfillment event exists” a strong MVP invariant.

There is still an unavoidable distributed-systems ambiguity if the payment provider accepts a charge immediately before OilSignal crashes or fails to commit locally. Production payment services therefore must keep the idempotency/replay semantics described below so a buyer can safely retry the same evidence-bound requirement.

The audit stores non-secret reconciliation metadata only: event ID, timestamp, external ID, SKU, evidence digest, amount/currency, resource path, protocol, optional gateway reference, and optional non-secret payer identity. Buyer credentials, protocol receipt headers, operator gateway bearer tokens, private keys, and provider response bodies are not stored.

`external_id` is an evidence identity, not a unique purchase ID. Multiple successful fulfillment events may legitimately share it, so the audit must not be treated as a revenue ledger. Reconcile it with the payment provider's settlement records using `external_id` and `gateway_reference`.

Operators can inspect the local audit without exposing payer/reference metadata over an unauthenticated HTTP admin endpoint:

```bash
oilsignal commerce-audit --data-dir ./data
oilsignal commerce-audit --data-dir ./data --gateway-reference settlement-123
oilsignal commerce-audit --data-dir ./data --external-id 'oilsignal:<sku>:sha256:<digest>'
```

See [`commerce-audit.md`](commerce-audit.md) for storage fields, retry semantics, CLI filters, and the SQLite deployment boundary.

## Free conditional revalidation

OilSignal checks the Evidence Pack's semantic ETag before payment verification.

A matching `If-None-Match` returns 304 without calling the payment service or appending a fulfillment audit event. The remote verifier is therefore invoked only when the buyer is about to receive changed semantic evidence:

```text
poll -> unchanged -> 304 -> no payment service call / no audit event
poll -> changed -> 402/verify -> audit commit -> paid fulfillment
```

## Security responsibilities of the payment service

A production payment service still must handle:

1. **Authenticity** — reject forged or malformed credentials/signatures.
2. **Replay protection** — prevent a single-use credential/payment from authorizing unintended repeat purchases when the rail requires single use.
3. **Requirement binding** — bind settlement to amount, currency, resource, and OilSignal `external_id`/evidence digest.
4. **Settlement state** — do not return success before the rail-specific success condition is satisfied.
5. **Idempotency** — safely handle retries and network/storage ambiguity, including a verified payment followed by an OilSignal audit-write failure.
6. **Secret handling** — keep private keys, wallet material, card/provider secrets, and raw credentials out of logs and returned metadata.
7. **Currency/amount validation** — verify the exact `PaymentRequirement` rather than trusting buyer-supplied price fields.
8. **Auditability** — return a stable non-secret `reference` when available so an operator can reconcile fulfillment with provider records.

OilSignal's HTTP bridge intentionally does not custody keys, create wallets, charge cards, submit blockchain transactions, or invent settlement success.

## Failure mapping

```text
missing declared buyer credential -> 402 without remote verification call
remote /verify HTTP 402          -> 402 plus a fresh challenge
remote transport/non-2xx         -> 503
malformed remote payload/header  -> 503
protocol/external-id mismatch    -> 502 enforced by OilSignal
reserved-header collision        -> 502 enforced by OilSignal
local fulfillment-audit failure  -> 503 before evidence is served
```

## Custom in-process integration

A hosted deployment can still bypass the HTTP bridge and construct the app with a native adapter:

```python
app = create_app(
    data_dir=...,
    agent_unit_price_usd=...,
    payment_gateway=my_gateway,
)
```

Custom gateways get the same OilSignal fulfillment-audit behavior because the audit is enforced at the API fulfillment boundary, not inside `HttpPaymentGateway`.

Use `oilsignal.api.app:app` only when you intentionally want the ungated core module-level application. Use `oilsignal.api.server:app` for normal runtime configuration, including the optional HTTP payment bridge.

## Next after MVP

Keep payment rails separate from the evidence schema and fulfillment audit. Useful hosted follow-ups are:

- move commerce audit state to the hosted server database for horizontally distributed deployments;
- add real MPP, x402, or organization-credit services behind the existing remote gateway contract;
- add SKU/contract-specific price policies without changing Evidence Pack schemas;
- optionally add seller-signed fulfillment receipts when buyers need cryptographic proof independent of the payment rail.
