# Portable evidence signatures

OilSignal can optionally sign the **semantic evidence identity** of every machine product with Ed25519. This lets a buyer persist an Evidence Pack, move it through another agent or storage system, and later prove that its evidence digest was signed by the configured OilSignal publisher.

This is a trust/distribution primitive, not a trading or settlement feature.

## Why detached signatures

The existing `evidence_sha256` remains the canonical semantic identity. Enabling or rotating a signing key therefore does **not** mutate petroleum evidence, product-state ETags, prices, or payment requirements.

When signing is enabled, two public routes are added:

```text
GET /.well-known/oilsignal-evidence-key.json
GET /api/agent/products/{sku}/signature
```

The first exposes the current Ed25519 public verification key. The second rebuilds the current fail-closed Evidence Pack and returns a detached signature bound to its exact `evidence_sha256`.

The signed message is domain-separated and versioned:

```text
oilsignal-evidence-v1
sha256:<evidence_sha256>
```

A signature therefore cannot be confused with an arbitrary Ed25519 signature over unrelated bytes.

## Configuration

Install the optional crypto capability:

```bash
pip install -e './backend[crypto]'
```

Provide `OILSIGNAL_AGENT_EVIDENCE_SIGNING_PRIVATE_KEY` as base64 of a raw 32-byte Ed25519 private key. Keep it in a secret manager or injected environment; never commit it.

`OILSIGNAL_AGENT_EVIDENCE_SIGNING_KEY_ID` is an optional stable rotation label. If omitted, OilSignal derives a non-secret ID from the public-key fingerprint.

Without a private key the signing routes return 404 and the rest of OilSignal works unchanged.

## Verification model

A buyer should:

1. fetch evidence and validate the existing evidence digest/ETag contract;
2. fetch the detached signature for the same SKU;
3. require the signature's `evidence_sha256` to equal the evidence digest it intends to trust;
4. obtain the verification key through a trusted discovery path;
5. verify the Ed25519 signature.

The signature proves possession of the configured private key for that evidence identity. It does not prove that upstream EIA data is correct, that a payment settled, or that the evidence implies any investment action.

## Rotation

Key rotation intentionally does not change evidence identity. Buyers that pin keys should retain the old public key for previously archived signatures and adopt the new key according to their own trust policy. A future hosted trust service can publish a signed key history without changing the Evidence Pack schema.
