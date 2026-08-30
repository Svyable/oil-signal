# Agent Catalog Change Manifest

OilSignal exposes a catalog-wide machine state at:

```text
GET /api/agent/manifest
```

The manifest is the cheapest way for another agent or service to answer:

> Did anything I could buy or consume change?

Instead of polling every SKU independently, a buyer can poll one weak ETag. When the manifest is unchanged OilSignal returns `304 Not Modified` with no body. When it changes, the buyer can inspect only the affected products and fetch or purchase those SKUs.

## What each entry contains

Each product entry includes:

- SKU and product kind;
- state, evidence, and quote paths;
- availability (`available`, `stale`, or `unavailable`);
- observation `as_of` when buildable;
- exact `state_sha256`;
- exact `evidence_sha256`;
- current price when configured;
- payment enforcement and protocol names;
- fulfillment/purchase availability.

The manifest does **not** contain the paid Evidence Pack's claims or observations.

## Digest semantics

`manifest_sha256` is deterministic over the ordered product entries. Its response contract is:

```text
ETag: W/"sha256:<manifest_sha256>"
X-OilSignal-Manifest-SHA256: <manifest_sha256>
Cache-Control: private, max-age=0, must-revalidate
```

A manifest changes when a product's relevant machine state changes, including:

- new petroleum evidence;
- price or payment-term changes that alter product state;
- freshness / fulfillment availability changes;
- product buildability changes;
- SKU additions or removals.

Evidence identity and commercial state remain separate. A price-only change can therefore change `state_sha256` and `manifest_sha256` while leaving `evidence_sha256` unchanged.

## Buyer loop

```python
from oilsignal.agent.buyer import OilSignalBuyer

previous = None
etag = None

with OilSignalBuyer("https://oilsignal.example") as buyer:
    poll = buyer.poll_manifest(etag=etag)
    if poll.not_modified:
        raise SystemExit(0)

    current = poll.manifest
    assert current is not None

    changed = (
        [entry.sku for entry in current.products]
        if previous is None
        else current.changed_skus_since(previous)
    )

    for sku in changed:
        try:
            entry = current.entry(sku)
        except KeyError:
            # The SKU was removed from the current catalog.
            continue

        if not entry.fulfillment_available:
            continue

        # Apply the buyer's own budget / relevance policy before fulfillment.
        # Then use buyer.fetch_evidence(...), supplying credentials if required.
```

The consuming system should persist the prior typed manifest and ETag if it wants local diffing across runs.

## Partial product failures

The dataset itself must exist for the manifest to be built. Once data is readable, however, one product that cannot be constructed does not hide every other product.

OilSignal records that SKU as `availability="unavailable"` with a non-secret reason while continuing to publish buildable entries. Unexpected programming/runtime exceptions are not swallowed as product unavailability; they remain server errors so defects are visible.

For stale live WPSR data, manifest/state discovery remains available, but affected product entries report that fulfillment is not available. The actual evidence fulfillment path continues to enforce OilSignal's fail-closed freshness behavior.

## Commercial use

The manifest is intentionally a primitive rather than a subscription database. It supports several deployment models without locking the open core to one vendor:

1. **Poll-to-buy:** an agent revalidates the manifest and purchases only changed SKUs.
2. **Hosted subscriptions:** a hosted service can watch manifest changes and enqueue signed notifications for subscribed SKUs.
3. **Use-case bundles:** a buyer can watch a selected SKU set and apply its own spend ceiling before fulfillment.
4. **Agent interoperability:** MCP/A2A adapters can expose the same deterministic state rather than inventing a second evidence model.

The manifest does not make trading decisions, execute orders, or decide whether an evidence product is economically worth purchasing. It is a change-detection and integrity surface for petroleum intelligence products.
