# OilSignal

> **An evidence-first agent for U.S. petroleum fundamentals.** Ingest public oil data, calculate what changed, and generate operational briefs where every market claim carries its evidence.

OilSignal is open-source decision-support software for fuel procurement teams, regional marketers, storage/terminal operators, consultants, and analysts who need a fast, auditable explanation of crude, product inventory, refinery, import, and demand changes. It is **not** a trading bot, does not execute trades, and does not provide price predictions or investment recommendations.

![Dashboard placeholder](https://placehold.co/1200x650/0b0f12/77d7b9?text=OilSignal+dashboard+%E2%80%94+replace+with+real+screenshot)

## Why OilSignal

Raw petroleum releases are useful but fragmented. OilSignal keeps the calculation chain explicit:

```mermaid
flowchart LR
    EIA[EIA public data] --> ING[Idempotent ingestion]
    ING --> STORE[Raw cache + Parquet + provenance]
    STORE --> CALC[Deterministic analytics]
    CALC --> CLAIM[Typed claims + citations]
    CLAIM --> GATE[Claim validator]
    GATE --> BRIEF[Briefs / composite alerts / Q&A]
    BRIEF --> UI[React dashboard]
```

A model can help explain evidence, but it is never the source of truth. OilSignal works without an LLM using deterministic report templates.

## What is implemented

- Typed petroleum observations with source URL, series ID, observation date, fetch time, and raw SHA-256.
- Idempotent offline fixture ingestion and configurable live EIA v2 ingestion into Parquet with SQLModel run metadata.
- EIA route/facet discovery CLI so production mappings can be verified against the API instead of hardcoded blindly.
- Fail-closed live ingestion for truncated API responses, duplicate periods from under-constrained facets, invalid frequencies, and non-numeric values.
- Transparent week-over-week, four-week average, year-over-year, seasonal-range, and z-score calculations.
- Structured `CalculationTrace`, `Citation`, `Claim`, and `Report` models.
- Claim validator that rejects uncited market claims and unlinked calculation claims.
- Weekly Petroleum Brief, Distillate Supply Risk Brief, and Refinery Utilization Watch in JSON, Markdown, and HTML.
- Single-signal threshold rules plus composite `all`/`any` alert policies with per-condition audit traces.
- FastAPI report, alert-evaluation, readiness, and cited Q&A endpoints.
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

Run the API:

```bash
uvicorn oilsignal.api.app:app --reload --port 8000
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

Discover a current EIA route and its facets:

```bash
oilsignal eia-metadata --route petroleum/sum/sndw
oilsignal eia-metadata --route petroleum/sum/sndw --facet <facet-id>
```

Create a registry from [`examples/eia-series.example.json`](examples/eia-series.example.json), constrain each canonical series to one row per period, then ingest:

```bash
oilsignal ingest-eia --registry ./my-eia-series.json --data-dir ./data
```

OilSignal retains raw JSON per configured series, hashes the source payload into each observation, and stores a public dataset URL without the API key. If EIA reports more rows than were returned, ingestion fails rather than accepting a silently truncated history. See [`docs/eia-setup.md`](docs/eia-setup.md).

## API examples

Generate the structured weekly report:

```bash
curl http://localhost:8000/api/reports/weekly
```

Render Markdown:

```bash
curl "http://localhost:8000/api/reports/weekly/render?format=markdown"
```

Ask a deterministic question against ingested evidence:

```bash
curl -X POST http://localhost:8000/api/ask \
  -H 'content-type: application/json' \
  -d '{"question":"Explain Midwest diesel tightness this week"}'
```

The response contains both `answer` and structured `evidence` objects.

## Composite alerts

Alert policies are data, not code. The included example requires both a low PADD 2 distillate inventory signal and soft refinery utilization:

```bash
oilsignal alerts-evaluate --rules examples/alerts.example.json --data-dir ./data
```

Or evaluate a policy set through `POST /api/alerts/evaluate`. Every policy response includes each condition's series ID, metric field, comparison operator, threshold, observed value, observation date, and match result. Missing series fail that condition instead of being inferred.

## Scheduling

The CLI is intentionally cron-friendly:

```bash
0 6 * * 3 cd /srv/oil-signal && .venv/bin/oilsignal ingest-eia --registry config/eia.json --data-dir data
0 7 * * 1 cd /srv/oil-signal && .venv/bin/oilsignal report --type weekly --format markdown --data-dir data > /var/reports/oilsignal-weekly.md
```

Managed email/Slack/Teams delivery can plug into the same validated report and alert boundaries; the community core does not need a hosted service to generate or inspect them.

## Repository layout

```text
backend/oilsignal/
├── agent/          # typed tools, validator, optional LLM client
├── alerts/         # threshold rules, composite policies, delivery protocol
├── analytics/      # deterministic petroleum time-series calculations
├── api/            # FastAPI endpoints
├── data_ingestion/ # EIA client/registry/live ingestion + offline fixtures
├── reports/        # cited report builders + renderers
└── storage/        # Parquet dataset utilities + SQLModel metadata
frontend/           # React + TypeScript + Vite
examples/           # offline ingestion, EIA registry, alert policies
tests/              # network-free fixtures and acceptance tests
docs/               # architecture, provenance, safety, open-core model
```

## Safety and product boundary

OilSignal v1 is for **operational decision support**. It deliberately excludes order execution, buy/sell recommendations, portfolio sizing, and price prediction. Missing evidence must fail closed or omit a section instead of creating a plausible number. See [`docs/agent-safety.md`](docs/agent-safety.md).

## Open core

Community code is Apache-2.0 with no artificial feature lockouts. A commercial hosted product can charge for reliability, scheduled delivery, organization workspaces, SSO/RBAC, private/vendor data connectors, managed retention, VPC/on-prem deployment, and enterprise support. See [`docs/open-core.md`](docs/open-core.md).

## Roadmap

1. Verify and publish maintained production EIA petroleum registries for crude, gasoline, distillate, jet fuel, imports, product supplied, utilization, and PADD inventories.
2. Add release-calendar-aware scheduling, freshness/SLA checks, and stale-data suppression for alerts.
3. Add richer configurable multi-signal policies, cooldown/deduplication, and delivery receipts.
4. Expand the evaluation suite for claim coverage, citation accuracy, alert reproducibility, and explanation faithfulness.
5. Add optional private connectors and organization knowledge boundaries.
6. Add facility/emissions intelligence using public EPA data after the fundamentals workflow is mature.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
