# OilSignal commercial offering

OilSignal turns public U.S. petroleum fundamentals into **auditable decision support** for teams and software agents that need to know what changed, why it matters operationally, and exactly which source observations support the answer.

The commercial wedge is not another market-data terminal. It is a trustable evidence layer that can sit between public petroleum releases and a procurement, supply, research, or automated-agent workflow.

## Who it is for

### Downstream fuel operators

Fuel procurement, regional marketing, terminal operations, and treasury teams that repeatedly assemble the same inventory, refinery, and demand facts after weekly petroleum releases.

**Decision supported:** whether current fundamentals deserve closer procurement, allocation, or regional supply attention.

**Value hypothesis:** spend less time assembling evidence and more time acting on a shared, cited view of the release.

### Petroleum analysts and consultants

Researchers who reconcile crude flows, inventories, refinery activity, and demand proxies for internal or client-facing work.

**Decision supported:** how the current crude and product fundamentals line up, including what remains unexplained by the modeled components.

**Value hypothesis:** make recurring calculations reproducible and make every material numeric statement easier to defend.

### Agent and automation builders

AI product and data-platform teams that need typed petroleum facts or deltas without scraping dashboards or trusting uncited model prose.

**Decision supported:** whether a petroleum evidence identity or its commercial state changed enough to fetch, verify, and potentially pay for new fulfillment.

**Value hypothesis:** integrate a small, cacheable, machine-verifiable evidence contract instead of rebuilding petroleum provenance logic.

## Three solution offers

### 1. Downstream Supply Risk

Recommended products:

- `weekly-petroleum-delta`
- `distillate-risk-evidence`
- `fact-padd2-distillate-stocks`
- `fact-us-refinery-utilization`
- `fact-us-distillate-product-supplied`

Use this when the buyer cares about weekly operational tightness more than a broad research report.

### 2. Crude Flow Reconciliation

Recommended products:

- `crude-balance-evidence`
- `fact-us-crude-production`
- `fact-us-crude-imports`
- `fact-us-crude-exports`
- `fact-us-crude-refinery-input`
- `fact-us-crude-stocks`

OilSignal deliberately describes the crude balance as a **partial deterministic reconciliation**, not an official EIA accounting identity. The other/adjustment residual remains visible rather than being explained away.

### 3. Agent-ready Petroleum Evidence

Recommended products:

- `weekly-petroleum-delta`
- `fact-us-crude-stocks`
- `fact-us-gasoline-stocks`
- `fact-us-distillate-stocks`
- `fact-us-refinery-utilization`

This offer is optimized for machine consumption: discovery, quote/state endpoints, catalog-wide change polling, semantic ETags, source hashes, evidence fingerprints, optional HTTP 402 commerce, and optional Ed25519 evidence signatures.

## What the buyer is actually buying

OilSignal's value contract is evidence quality and workflow compression, not a prediction promise.

A useful evaluation asks whether OilSignal improves:

- **speed:** time from a release becoming usable to an auditable decision-support output;
- **effort:** analyst minutes and manual source lookups per weekly cycle;
- **auditability:** share of material numeric claims traceable to source observations and calculations;
- **freshness discipline:** stale or unverifiable outputs blocked before they are used;
- **automation:** recurring downstream steps that can consume the same stable evidence contract.

OilSignal does not promise trading returns, price forecasts, or automated execution.

## Founding-customer motion

Start with **one decision and one narrow evidence set**. Run OilSignal in parallel with the buyer's existing workflow for 2-4 weekly release cycles.

1. Baseline the current manual process and its source checks.
2. Pick one of the three solution offers above.
3. Configure only the necessary SKUs.
4. Run both workflows on the same release cycles.
5. Measure speed, analyst effort, stale-data handling, and evidence traceability.
6. Expand only if the buyer can point to a recurring workflow that improved.

For the first paid or design-partner customer, OilSignal already supports a scoped founding-pilot access credential and durable fulfillment audit. See [`docs/founding-pilot.md`](docs/founding-pilot.md).

## Packaging ladder

### Open core

Self-hosted ingestion, deterministic analytics, cited reports, local alerts, Q&A, agent discovery, and evidence products remain the credibility and adoption layer.

### Founding pilot

A narrow set of priced SKUs, explicit customer entitlement, operator-controlled commercial agreement, and audited fulfillment. This is the fastest path to learning what a real buyer values before building a full account system.

### Hosted team product

The natural paid expansion is managed operations around the open core: team workspaces, managed ingestion and freshness, alert destinations, private connectors, SSO, permissions, history, collaboration, and support.

### Embedded evidence API

For software agents and data products, use per-SKU or usage-oriented pricing around changed, verified evidence rather than charging for repeated unchanged polling.

### Enterprise deployment

Private cloud/VPC/on-prem deployment, private connectors, support commitments, and operational controls can serve organizations that cannot use a shared hosted service.

## Machine discovery

The configurable runtime server exposes the commercial catalog at:

```text
GET /.well-known/oilsignal-commercial.json
GET /api/agent/offers
```

Each solution maps directly to existing OilSignal SKUs and quote paths. The public product catalog remains:

```text
GET /.well-known/oilsignal-agent.json
```

The catalog-wide change manifest remains:

```text
GET /api/agent/manifest
```

Commercial positioning therefore stays connected to the product surface instead of becoming a separate slide deck that drifts from implementation.
