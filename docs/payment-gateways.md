# Payment Gateway Adapters

OilSignal's paid Evidence Pack path is intentionally split into two responsibilities:

- **OilSignal core** defines the product, price, evidence digest, freshness policy, HTTP 402 orchestration, and receipt/evidence binding checks.
- A **PaymentGateway adapter** implements the actual machine-payment protocol, credential verification, settlement/credit consumption, replay protection, and protocol-specific HTTP headers.

The repository does not ship a fake production payment provider. Tests use in-memory adapters only to prove the boundary.

## Adapter interface

A gateway implements the protocol in `oilsignal.agent.commerce.PaymentGateway`:

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

`protocol` is the adapter identity advertised through the OilSignal product quote when HTTP 402 enforcement is active.

`credential_headers` lists request headers that can change authorization state. OilSignal emits them in `Vary` and accepts arbitrary protocol header names through CORS for configured local origins.

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

Adapters should include this value, or an unambiguous cryptographic commitment to it, in their provider-side payment intent/authorization metadata whenever the underlying protocol permits it.

The same requirement object is supplied to both `challenge()` and `verify()`.

## Challenge

When verification rejects a request, OilSignal calls:

```python
gateway.challenge(requirement)
```

The adapter returns:

```python
PaymentChallenge(
    protocol="...",
    response_headers={...},
    challenge_id="...",
)
```

`response_headers` are passed through on the 402 response after OilSignal verifies that they do not collide with reserved evidence/cache headers.

Examples of shapes that fit this interface include:

```text
MPP-shaped:
WWW-Authenticate: Payment ...

x402-v2-shaped:
PAYMENT-REQUIRED: ...
```

These examples describe adapter shapes tested by OilSignal. They are not built-in settlement implementations.

## Verification

For changed evidence, OilSignal calls:

```python
gateway.verify(dict(request.headers), requirement)
```

A verifier either:

- returns a `VerifiedPayment` only after the adapter's required authorization/settlement checks succeed;
- raises `PaymentRejected` when a new 402 challenge should be returned; or
- raises `PaymentGatewayUnavailable` when payment infrastructure is unavailable.

A successful result contains:

```python
VerifiedPayment(
    protocol="...",
    response_headers={...},
    external_id=requirement.external_id,
    reference="optional provider/settlement reference",
    payer="optional non-secret payer identity",
)
```

OilSignal checks both `protocol` and `external_id` before it serves the Evidence Pack. A mismatch fails with 502.

## Protocol-owned success headers

Adapters return their normal protocol success/receipt headers through `VerifiedPayment.response_headers`.

Examples of tested shapes:

```text
MPP-shaped:
Payment-Receipt: ...

x402-v2-shaped:
PAYMENT-RESPONSE: ...
```

OilSignal additionally emits vendor-neutral binding metadata:

```text
X-OilSignal-Payment-Protocol: <protocol>
X-OilSignal-Payment-External-ID: oilsignal:<sku>:sha256:<digest>
X-OilSignal-Payment-Reference: <optional reference>
X-OilSignal-Payment-Payer: <optional payer>
```

Do not put secrets, raw payment credentials, private keys, or bearer tokens into these OilSignal headers.

## Reserved headers

OilSignal rejects adapter response headers that attempt to override its evidence or representation boundary, including:

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
```

The rejection is intentional. A payment adapter must not be able to alter which evidence was purchased, weaken its cache semantics, or overwrite the digest that the receipt is being bound to.

## Free conditional revalidation

OilSignal checks the Evidence Pack's semantic ETag before calling `verify()`.

A matching `If-None-Match` returns 304 without payment verification. Adapters should therefore assume that their verifier is called only when the buyer is about to receive changed semantic evidence.

This creates a useful machine-buyer contract:

```text
poll -> unchanged -> 304 -> no charge
poll -> changed -> 402/verify -> paid fulfillment
```

## Security responsibilities

A production adapter must handle at least:

1. **Authenticity** — reject forged or malformed credentials/signatures.
2. **Replay protection** — prevent a single-use credential/payment from authorizing unintended repeat purchases when the protocol requires single use.
3. **Requirement binding** — bind settlement to amount, currency, resource, and OilSignal `external_id`/evidence digest.
4. **Settlement state** — do not return `VerifiedPayment` before the adapter's protocol-specific success condition is satisfied.
5. **Idempotency** — safely handle retries and network ambiguity according to the payment rail's semantics.
6. **Secret handling** — keep private keys, bearer tokens, wallet material, card/provider secrets, and raw credentials out of logs and OilSignal response metadata.
7. **Timeout/error mapping** — raise `PaymentGatewayUnavailable` for provider/network failures rather than treating them as successful or ordinary buyer rejection.
8. **Header hygiene** — return only protocol-owned response headers and do not collide with OilSignal reserved headers.
9. **Currency/amount validation** — verify the exact `PaymentRequirement` rather than trusting client-supplied price fields.
10. **Auditability** — provide a stable non-secret `reference` when the provider has one so a hosted operator can reconcile fulfillment with payment records.

## Failure mapping

Adapters should use the narrow OilSignal exceptions:

```text
PaymentRejected           -> 402 plus a fresh challenge
PaymentGatewayUnavailable -> 503
protocol/external-id mismatch -> 502 enforced by OilSignal
reserved-header collision -> 502 enforced by OilSignal
```

Unexpected adapter exceptions are programming faults and should not be converted into successful fulfillment.

## Production integration pattern

A hosted deployment should construct the application with its real adapter:

```python
app = create_app(
    data_dir=...,
    agent_unit_price_usd=...,
    payment_gateway=my_gateway,
)
```

The default module-level `app = create_app()` intentionally has no payment gateway. This preserves the self-hosted open-core behavior and prevents a repository checkout from pretending it can settle payments.

## What to build next

Production adapters should remain separate from the evidence schema. That allows OilSignal to add or replace payment rails without changing the purchased intelligence object.

Useful next implementations are:

- one real hosted MPP adapter with provider/network replay protection;
- one real hosted x402 v2 adapter with verification/settlement integration;
- organization credit-account adapters for non-crypto enterprise deployments;
- durable purchase/receipt audit storage keyed by `external_id`;
- SKU-specific price policies and volume/contract pricing.
