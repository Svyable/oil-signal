# OilSignal

> **An evidence-first agent for U.S. petroleum fundamentals.** Ingest public oil data, calculate what changed, and generate operational briefs where every market claim carries its evidence.

OilSignal is open-source decision-support software for fuel procurement teams, regional marketers, storage/terminal operators, consultants, analysts, and software agents that need a fast, auditable explanation of crude, product inventory, refinery, import/export, production, and demand changes. It is **not** a trading bot, does not execute trades, and does not provide price predictions or investment recommendations.

![Dashboard placeholder](https://placehold.co/1200x650/0b0f12/77d7b9?text=OilSignal+dashboard+%E2%80%94+replace+with+real+screenshot)

## Why OilSignal

Raw petroleum releases are useful but fragmented. OilSignal keeps the calculation chain explicit:

```mermaid
flowchart LR
    EIA[EIA public data] --> ING[Idempotent ingestion]
    ING --> STORE[Raw cache + Parquet + provenance]
    STORE --> FRESH[Release-aware freshness gate]
    FRESH --> CALC[Deterministic analytics]
    CALC --> CLAIM[Typed claims + citations]
    CLAIM --> GATE[Claim validator]
    GATE --> BRIEF[Briefs / composite alerts / Q&A]
    BRIEF --> PACK[Agent Evidence Packs]
    PACK --> COMMERCE[Evidence-bound HTTP 402 gateway]
    BRIEF --> UI[React dashboard]
    BRIEF --> OUTBOX[Transactional alert outbox]
    OUTBOX --> LEASE[Worker lease + backoff]
    LEASE --> ADAPTER[Delivery adapter / dead letter]
```

A model can help explain evidence, but it is never the source of truth. OilSignal works without an LLM using deterministic report templates.

## Commercial value

OilSignal is designed to sell a **better recurring decision workflow**, not another undifferentiated oil-data screen. The initial value offering is organized around three concrete decisions:

- **Downstream Supply Risk** — help fuel procurement, regional marketing, terminal operations, and treasury teams assess whether weekly inventory, refinery, and demand changes deserve closer operational attention.
- **Crude Flow Reconciliation** — help analysts and consultants reproduce how production, imports, exports, refinery input, and commercial stock change line up without hiding the residual or overstating a partial balance.
- **Agent-ready Petroleum Evidence** — give software agents typed petroleum facts and deltas with machine discovery, stable state/evidence identity, provenance, cache semantics, optional payment, and optional portable signatures.

The recommended founding-customer motion is deliberately narrow: choose one decision, run OilSignal in parallel with the buyer's current process for 2-4 weekly release cycles, and measure release-to-output latency, analyst effort, evidence traceability, stale-data handling, and recurring steps automated. Expand only when the buyer can identify a workflow that materially improved.

See [`COMMERCIAL.md`](COMMERCIAL.md) for the buyer-facing offer, [`docs/go-to-market.md`](docs/go-to-market.md) for the commercialization playbook, and [`docs/founding-pilot.md`](docs/founding-pilot.md) for first-customer entitlement and fulfillment.

## What is implemented

- Typed petroleum observations with source URL, series ID, observation date, fetch time, and raw SHA-256.
- Idempotent offline fixture ingestion and configurable live EIA v2 ingestion into Parquet with SQLModel run metadata.
- A maintained weekly EIA registry for crude stocks, field production, imports, exports, refinery crude input, gasoline, distillate, PADD 2 distillate, jet fuel, refinery utilization, and national gasoline/distillate/jet/total-product-supplied demand proxies.
- Executable EIA registry verification that probes every configured route, validates sample shape/numeric data, captures API warnings/version, and optionally enforces WPSR recency.
- A scheduled/manual GitHub workflow for live registry verification when repository secret `EIA_API_KEY` is configured.
- EIA route/facet discovery CLI for extending and re-verifying mappings.
- Fail-closed live ingestion for truncated responses, duplicate periods, invalid frequencies, and non-numeric values.
- Release-calendar-aware WPSR freshness checks with a two-hour EIA API grace window and explicit holiday overrides.
- Provenance-aware live/fixture discrimination so synthetic development data is never treated as a live WPSR feed.
- Transparent week-over-week, four-week average, year-over-year, seasonal-range, and z-score calculations.
- A cited Crude Balance Watch that aligns production/import/export/refinery-input weeks, computes a transparent core-flow balance, converts commercial-stock change to a daily-equivalent rate, and exposes the remaining other/adjustment residual without claiming an official EIA balance identity.
- Structured `CalculationTrace`, `Citation`, `Claim`, and `Report` models.
- Claim validator that rejects uncited market claims and unlinked calculation claims.
- Weekly Petroleum Brief, Weekly Petroleum Delta, Distillate Supply Risk Brief, Refinery Utilization Watch, and Crude Balance Watch; live briefs opportunistically include the broader maintained fundamentals set.
- Agent-native brief, delta, and maintained single-series fact SKUs with well-known discovery, product-state polling, configurable quote metadata, claim/calculation fingerprints, cited raw-source hashes, stable semantic SHA-256 digests, and weak ETag/304 cache revalidation.
- Catalog-wide machine change manifest for cheap polling of evidence and commercial state across all SKUs.
- Machine-readable commercial discovery that maps three solution offers to real SKUs, quote paths, proof points, and pilot success metrics.
- Optional Ed25519 detached evidence signatures for portable verification of archived evidence identity.
- Static per-SKU pricing overrides with a global fallback, explicit unpriced overrides, fail-closed unknown-SKU validation, and price-sensitive product-state fingerprints.
- Protocol/header-neutral HTTP 402 orchestration with payment requirements bound to SKU, normalized price terms, and `evidence_sha256`; adapter-owned credential/challenge/receipt headers; receipt-binding checks; protected provenance headers; and free unchanged-data revalidation before payment verification.
- Founding-pilot scoped entitlement mode for the first paid/design-partner customer before a full account/payment system is required.
- Durable append-only paid-fulfillment audit records with evidence digest, price/currency, protocol, gateway reference, and non-secret reconciliation identity.
- Single-signal threshold rules plus composite `all`/`any` alert policies with per-condition audit traces.
- Edge-triggered alert state with recovery/re-arm behavior and duplicate suppression.
- Transactional alert outbox with at-least-once delivery, local multi-worker leases, bounded exponential backoff, dead-letter history, requeue, and delivery receipts.
- FastAPI report, alert-evaluation, readiness, agent-product, commercial-offer, and cited Q&A endpoints.
- React/Vite dashboard showing claims and the evidence table.
- Optional OpenAI-compatible LLM client for local or hosted endpoints.
- Docker Compose, pytest, Ruff, mypy, pre-commit, and GitHub Actions.

The included petroleum fixture is **synthetic test data**, including its development-only `PET.*` identifiers. It exists so tests and the demo run with no network access and must not be presented as current EIA data.

## Quick start: Docker

```bash
git clone https://github.com/Svyable/oil-signal.git
cd oil-signal
docker compose up --build
```

Open:

- Dashboard: `http://localhost:3000`
- FastAPI docs: `http://localhost:8000/docs`
- Agent product discovery: `http://localhost:8000/.well-known/oilsignal-agent.json`
- Commercial solution discovery: `http://localhost:8000/.well-known/oilsignal-commercial.json`
- Catalog-wide change manifest: `http://localhost:8000/api/agent/manifest`
- Liveness: `http://localhost:8000/health`
- Data readiness: `http://localhost:8000/health/ready`

On an empty data volume, Compose loads the synthetic fixture once so the UI is immediately usable. Delete the `oilsignal-data` volume when you intentionally want a clean local data store.

## Local Python development

Python 3.12 is required.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e "./backend[dev]"
pytest
ruff check backend tests examples
mypy backend/oilsignal
```

Load the offline fixture and generate a cited brief:

```bash
export OILSIGNAL_DATA_DIR=./data
python examples/ingest_fixture.py
python examples/generate_weekly_brief.py
```

The installed CLI can render the same report path:

```bash
oilsignal report --type weekly --format markdown --data-dir ./data
```

Run the configurable API runtime (payment, pilot, signature, and commercial discovery settings are applied here):

```bash
uvicorn oilsignal.api.server:app --reload --port 8000
```

Run the web UI in another shell:

```bash
cd frontend
npm install
npm run dev
```

## Live EIA ingestion

Tests and the synthetic demo do not require a key. For live connector use:

```bash
export OILSIGNAL_EIA_API_KEY=your-key
```

Verify the maintained source contract, ingest it, and check the resulting dataset:

```bash
oilsignal eia-verify-registry --registry examples/eia-series.example.json
oilsignal ingest-eia --registry examples/eia-series.example.json --data-dir ./data
oilsignal freshness --data-dir ./data
```

For extension or debugging, inspect EIA routes/facets directly:

```bash
oilsignal eia-metadata --route petroleum/sum/sndw
oilsignal eia-metadata --route petroleum/sum/sndw --facet <facet-id>
```

The verifier checks every route independently and returns a complete audit rather than hiding later failures behind the first broken series. `.github/workflows/eia-registry-verify.yml` can run the probe manually or on its Friday schedule when repository secret `EIA_API_KEY` is configured.

OilSignal retains raw JSON per configured series, hashes source payloads into observations, and stores public dataset URLs without the API key. If EIA reports more rows than were returned, ingestion fails rather than accepting silently truncated history.

For live EIA runs, report, Q&A, alert, and agent Evidence Pack paths fail closed when the latest weekly evidence trails the expected WPSR week after the configured publication time plus the two-hour API grace window. Synthetic fixture runs are explicitly excluded from the live freshness gate by ingestion provenance. See [`docs/eia-setup.md`](docs/eia-setup.md) and [`docs/freshness.md`](docs/freshness.md).

## Reports and API examples

Generate the structured weekly report:

```bash
curl http://localhost:8000/api/reports/weekly
```

Generate the crude flow reconciliation:

```bash
oilsignal report --type crude-balance --format markdown --data-dir ./data
curl http://localhost:8000/api/reports/crude-balance
```

The Crude Balance Watch uses:

```text
core flow balance = production + imports - exports - refinery input
```

It then compares that partial flow result with the daily-equivalent change in commercial crude stocks and reports the difference as an **other/adjustment residual**. That residual is not a forecast error, a trading signal, or an official EIA balance component. See [`docs/crude-balance.md`](docs/crude-balance.md).

Render the standard weekly brief as Markdown:

```bash
curl "http://localhost:8000/api/reports/weekly/render?format=markdown"
```

Ask a deterministic question against ingested evidence:

```bash
curl -X POST http://localhost:8000/api/ask \
  -H 'content-type: application/json' \
  -d '{"question":"What is the crude balance this week?"}'
```

The response contains both `answer` and structured `evidence` objects. Explicit crude production, export, refinery-input, and crude-balance questions route to the corresponding maintained evidence rather than an inventory substitute.

## Agent-native Evidence Packs and facts

OilSignal packages its deterministic intelligence into stable machine products instead of requiring another agent to scrape the dashboard or reverse-engineer report prose. Broader briefs, event deltas, and small maintained single-series facts use the same evidence, state, quote, payment, and audit contracts.

Discover the product catalog and the buyer-oriented solution catalog:

```bash
curl http://localhost:8000/.well-known/oilsignal-agent.json
curl http://localhost:8000/.well-known/oilsignal-commercial.json
```

The commercial catalog is positioning metadata, not a second pricing authority. Each solution references real SKUs and their quote paths; actual commercial terms continue to resolve through the ordinary product quote/state/payment path.

Configure a fallback price plus cheaper or premium SKU overrides:

```bash
export OILSIGNAL_AGENT_EVIDENCE_PACK_PRICE_USD='0.05'
export OILSIGNAL_AGENT_SKU_PRICES='{"fact-us-crude-stocks":"0.005","fact-padd2-distillate-stocks":"0.0075","crude-balance-evidence":"0.10"}'
export OILSIGNAL_AGENT_PRICE_CURRENCY='USD'

curl http://localhost:8000/api/agent/products/fact-us-crude-stocks/quote
curl http://localhost:8000/api/agent/products/crude-balance-evidence/quote
```

An exact SKU override wins over the fallback. A JSON `null` override keeps that SKU unpriced even when the fallback exists. Unknown override SKUs fail app construction rather than silently charging the fallback amount.

A price alone remains metadata and does **not** gate the open-core endpoint. HTTP 402 enforcement activates for a priced SKU only when the application is also constructed with a real `PaymentGateway` adapter. An explicitly unpriced SKU remains open even when other products on the same process are paid.

Poll the catalog-wide manifest when a buyer wants to know whether any relevant evidence or commercial state changed, then drill into a SKU only when necessary:

```bash
curl -i http://localhost:8000/api/agent/manifest
curl -i http://localhost:8000/api/agent/products/fact-us-crude-stocks/state
```

`state_sha256` includes the resolved price and payment terms, while `evidence_sha256` does not. A price-only change therefore invalidates `/state` without pretending the petroleum evidence changed. Agents that care about both evidence and commercial terms should poll `/state` or the catalog-wide manifest.

Fulfill the evidence product:

```bash
curl -i http://localhost:8000/api/agent/products/fact-us-crude-stocks/evidence
```

The evidence response carries a weak semantic `ETag` (`W/"sha256:..."`), `X-OilSignal-Evidence-SHA256`, and `X-OilSignal-SKU`. A buyer can send the previous evidence ETag via `If-None-Match`; unchanged semantic evidence returns `304 Not Modified` with no body **before payment verification**. Evidence ETags intentionally remain evidence-only, so use `/state` to detect price changes.

An Evidence Pack includes stable claim/calculation fingerprints, only the observations needed by its citations, each cited observation's ingestion `raw_hash`, release-aware freshness state, and a semantic `evidence_sha256`. Runtime timestamps, random internal report IDs, and price changes do not perturb that digest.

When commerce is active for a SKU, OilSignal validates/builds the fresh pack first and derives a payment operation ID from the exact SKU, normalized price terms, and evidence digest:

```text
oilsignal:<sku>:<CURRENCY>:<amount>:sha256:<evidence_sha256>
```

Equivalent decimals such as `0.0050` and `0.005` normalize to the same operation ID, while a real price change creates a different ID even if the evidence is unchanged. This avoids settlement/idempotency collisions across price changes. A rejected credential returns a 402 problem body without purchased claims/observations. The adapter owns its own payment headers, verification, settlement, and replay protection; OilSignal requires a successful receipt to echo the same operation ID before serving the pack.

The gateway interface is header-neutral. Tests exercise both MPP-shaped headers (`WWW-Authenticate` / `Authorization` / `Payment-Receipt`) and x402-v2-shaped headers (`PAYMENT-REQUIRED` / `PAYMENT-SIGNATURE` / `PAYMENT-RESPONSE`) without baking either protocol into the evidence layer. These are adapter-shape tests, not bundled production payment providers.

If evidence signing is configured, the runtime also exposes the current public verification key plus detached signatures bound to `evidence_sha256`. Signing authenticates the OilSignal evidence identity; it does not claim that upstream public data cannot contain errors. See [`docs/evidence-signatures.md`](docs/evidence-signatures.md).

See [`docs/agent-products.md`](docs/agent-products.md), [`docs/agent-fact-products.md`](docs/agent-fact-products.md), [`docs/agent-manifest.md`](docs/agent-manifest.md), [`docs/agent-pricing.md`](docs/agent-pricing.md), and [`docs/payment-gateways.md`](docs/payment-gateways.md).

## Composite alerts and worker delivery

Alert policies are data, not code. The included example requires both low PADD 2 distillate inventory and soft refinery utilization:

```bash
oilsignal alerts-evaluate --rules examples/alerts.example.json --data-dir ./data
```

Stateful evaluation atomically updates edge state and enqueues a durable outbox row on an inactive-to-active transition. A continuously true policy does not enqueue again until recovery/re-arm.

Preview without mutating state:

```bash
oilsignal alerts-evaluate --rules examples/alerts.example.json --data-dir ./data --stateless
```

Drain eligible rows with an explicit worker identity and retry policy:

```bash
oilsignal alerts-deliver \
  --adapter console \
  --data-dir ./data \
  --worker-id worker-1 \
  --lease-seconds 120 \
  --max-attempts 5 \
  --base-backoff-seconds 30 \
  --max-backoff-seconds 3600
```

Claims use short expiring SQLite leases, so multiple local processes sharing one metadata database cannot actively own the same notification. Failed rows back off exponentially; exhausted rows become dead letters.

```bash
oilsignal alerts-dead-letters --data-dir ./data
oilsignal alerts-requeue --outbox-id out_... --data-dir ./data
```

Delivery remains intentionally **at least once**. A crash after an external provider accepts a message but before local acknowledgement can still cause a retry, so production adapters should use provider idempotency based on `outbox_id`. See [`docs/alert-state.md`](docs/alert-state.md).

## Scheduling

The CLI is cron-friendly. A typical self-hosted flow is verify source contract → ingest → verify dataset freshness → evaluate/enqueue → deliver/retry → render:

```bash
# Wednesday after the normal WPSR/API grace window; adjust for your timezone/operations.
45 12 * * 3 cd /srv/oil-signal && .venv/bin/oilsignal eia-verify-registry --registry examples/eia-series.example.json
50 12 * * 3 cd /srv/oil-signal && .venv/bin/oilsignal ingest-eia --registry examples/eia-series.example.json --data-dir data
55 12 * * 3 cd /srv/oil-signal && .venv/bin/oilsignal freshness --data-dir data
0 13 * * 3 cd /srv/oil-signal && .venv/bin/oilsignal alerts-evaluate --rules config/alerts.json --data-dir data
5 13 * * 3 cd /srv/oil-signal && .venv/bin/oilsignal alerts-deliver --adapter console --data-dir data
10 13 * * 3 cd /srv/oil-signal && .venv/bin/oilsignal report --type weekly --format markdown --data-dir data > /var/reports/oilsignal-weekly.md
15 13 * * 3 cd /srv/oil-signal && .venv/bin/oilsignal report --type crude-balance --format markdown --data-dir data > /var/reports/oilsignal-crude-balance.md
```

The release-aware freshness gate—not the example clock—is the source of truth. Holiday-delayed weeks remain stale until the expected release and current evidence arrive.

Email/Slack/Teams implementations can plug into the same adapter/outbox boundary. The SQLite lease implementation is designed for multiple local workers sharing one database; a future horizontally distributed hosted deployment should use a server database/queue rather than treating SQLite as a distributed broker.

## Repository layout

```text
backend/oilsignal/
├── agent/          # evidence products, commercial discovery, commerce/pricing, signatures, validator, optional LLM client
├── alerts/         # threshold/composite rules, edge state, leased delivery
├── analytics/      # deterministic petroleum time-series + crude-flow reconciliation
├── api/            # FastAPI endpoints and configurable runtime assembly
├── data_ingestion/ # EIA client/registry/verification/live ingestion + fixtures
├── freshness.py    # WPSR release calendar and stale-data gate
├── reports/        # cited report/fact builders + renderers
└── storage/        # Parquet data + SQLModel state/outbox/leases/dead letters/commerce audit
frontend/           # React + TypeScript + Vite
examples/           # offline ingestion, maintained EIA registry, alert policies
tests/              # network-free fixtures and acceptance tests
docs/               # architecture, provenance, freshness, agent/commerce, GTM, and safety docs
```

## Safety and product boundary

OilSignal v1 is for **operational decision support**. It deliberately excludes order execution, buy/sell recommendations, portfolio sizing, and price prediction. Missing or stale live evidence must fail closed or omit a section instead of creating a plausible number. Partial balance calculations are labeled as such and must not be presented as official EIA accounting identities. See [`docs/agent-safety.md`](docs/agent-safety.md).

## Open core

Community code is Apache-2.0 with no artificial feature lockouts. A commercial hosted product can charge for reliability, scheduled delivery, organization workspaces, SSO/RBAC, private data connectors, managed retention, agent Evidence Pack fulfillment/payment infrastructure, VPC/on-prem deployment, and enterprise support. The recommended land-and-expand motion is open-core proof → narrow founding pilot → hosted team workflow or embedded evidence API → enterprise deployment where required. See [`docs/open-core.md`](docs/open-core.md) and [`docs/go-to-market.md`](docs/go-to-market.md).

## Roadmap

1. Convert the first real founding/design-partner pilot and prioritize the next product slice from measured customer workflow pull.
2. Add managed hosted delivery/team-workspace capabilities where early customers repeatedly ask for collaboration, history, permissions, or alert destinations.
3. Add production payment/account adapters for multi-customer operation while preserving the rail-independent evidence/payment requirement contracts.
4. Expand verified PADD crude/product coverage and add more explicit supply-disposition components without weakening canonical-series or citation contracts.
5. Generalize release calendars and freshness policies beyond WPSR-backed weekly series.
6. Expand the evaluation suite for claim coverage, citation accuracy, balance reconciliation, alert reproducibility, freshness behavior, commercial-state compatibility, and explanation faithfulness.
7. Add optional private connectors and organization knowledge boundaries when customer demand validates the integration surface.
8. Add facility/emissions intelligence using public EPA data after the fundamentals workflow and commercial wedge are proven.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
