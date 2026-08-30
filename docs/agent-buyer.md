# Agent Buyer Quickstart

OilSignal includes a small synchronous buyer helper for agents and integration tests that need to consume its machine products without reimplementing the HTTP contract.

The buyer is intentionally **payment-protocol neutral**. It understands OilSignal discovery, product state, semantic cache validation, HTTP 402 problem bodies, and evidence integrity. It does not know how to obtain an MPP, x402, pilot, card, credit, or other credential.

## Minimal loop

```python
from oilsignal.agent.buyer import BuyerPaymentRequired, OilSignalBuyer

with OilSignalBuyer("https://oilsignal.example") as buyer:
    state_result = buyer.poll_state("weekly-petroleum-delta")
    if state_result.not_modified:
        raise SystemExit(0)

    state = state_result.state
    assert state is not None

    try:
        result = buyer.fetch_evidence(
            state.sku,
            expected_evidence_sha256=state.evidence_sha256,
        )
    except BuyerPaymentRequired as challenge:
        print(challenge.problem)
        # Obtain a protocol credential outside this helper, then retry using
        # credential_headers={"<protocol header>": "<credential>"}.
        raise
```

`fetch_evidence()` only returns an `EvidencePack` after checking:

- the response `X-OilSignal-Evidence-SHA256` equals the pack body digest;
- the evidence ETag is exactly the weak semantic validator derived from that digest;
- when `expected_evidence_sha256` is supplied, fulfillment equals the digest previously observed through `/state`.

A mismatch raises `BuyerIntegrityError` rather than handing inconsistent evidence to the caller.

`poll_state()` similarly verifies the returned state/evidence digest headers against the typed state body.

## Free revalidation

Persist the returned product-state ETag in the buyer's own workflow:

```python
first = buyer.poll_state("weekly-petroleum-delta")
next_poll = buyer.poll_state("weekly-petroleum-delta", etag=first.etag)
if next_poll.not_modified:
    # Evidence + commercial state are unchanged.
    ...
```

The seller returns 304 with no body when the state is semantically unchanged.

Evidence has its own evidence-only ETag. The two validators remain intentionally separate because a price change should mutate product state without changing petroleum evidence identity.

## Handling 402

A 402 raises `BuyerPaymentRequired`. Its `.problem` is the typed OilSignal `PaymentProblem` containing:

- SKU;
- amount/currency;
- exact evidence digest;
- evidence-bound external operation ID;
- fulfillment path;
- payment protocol;
- challenge ID when the adapter supplies one.

Its `.headers` contains the seller's HTTP response headers so a protocol-specific integration can inspect its challenge header(s).

After the caller obtains an appropriate credential, retry:

```python
fulfilled = buyer.fetch_evidence(
    "weekly-petroleum-delta",
    credential_headers={"X-OilSignal-Pilot-Key": pilot_key},
    expected_evidence_sha256=state.evidence_sha256,
)
```

For another adapter the header name/value can be different. The buyer helper does not hard-code pilot, MPP, or x402 semantics.

## Command-line example

`examples/buy_agent_product.py` provides a standalone integration smoke test.

Open/free product:

```bash
python examples/buy_agent_product.py \
  --base-url http://localhost:8000 \
  --sku fact-us-crude-stocks
```

Founding pilot:

```bash
export OILSIGNAL_AGENT_CREDENTIAL_HEADER='X-OilSignal-Pilot-Key'
export OILSIGNAL_AGENT_CREDENTIAL='<pilot-secret>'
python examples/buy_agent_product.py \
  --base-url https://<host> \
  --sku weekly-petroleum-delta
```

For repeated polling, persist the printed state ETag and provide it as `--etag` or `OILSIGNAL_AGENT_STATE_ETAG` on the next run.

Do not put real credentials in repository files. Prefer environment injection or the secret-management mechanism of the calling agent/runtime.

## Scope

This is deliberately a small client helper, not a marketplace wallet or payment SDK. It does not:

- discover payment providers;
- sign transactions;
- hold private keys;
- settle payments;
- persist buyer credentials;
- automatically retry arbitrary 402 protocols;
- decide whether a product is worth buying.

Those decisions remain with the consuming agent. OilSignal provides the typed commercial/evidence boundary and verifies that the bytes returned to the buyer correspond to the evidence identity the buyer intended to consume.
