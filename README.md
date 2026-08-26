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
    GATE --> BRIEF[Briefs / alerts / Q&A]
    BRIEF --> UI[React dashboard]
```

A model can help explain evidence, but it is never the source of truth. OilSignal works without an LLM using deterministic report templates.

## What is implemented

- Typed petroleum observations with source URL, series ID, observation date, fetch time, and raw SHA-256.
- Idempotent offline fixture ingestion into Parquet with SQLModel ingestion metadata.
- Transparent week-over-week, four-week average, year-over-year, seasonal-range, and z-score calculations.
- Structured `CalculationTrace`, `Citation`, `Claim`, and `Report` models.
- Claim validator that rejects uncited market claims and unlinked calculation claims.
- Weekly Petroleum Brief in JSON, Markdown, and HTML.
- Rule-based threshold alerts with pluggable delivery interface and console adapter.
- FastAPI report and cited Q&A endpoints.
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
- Health check: `http://localhost:8000/health`

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

## EIA API key setup

Tests and the synthetic demo do not require a key. For live connector development:

```bash
cp .env.example .env
# edit .env and set EIA_API_KEY
```

For direct Python use, set `OILSIGNAL_EIA_API_KEY`. See [`docs/eia-setup.md`](docs/eia-setup.md) and [`examples/eia-series.example.json`](examples/eia-series.example.json). The example intentionally leaves route/series values as placeholders so the repository does not pretend a stale route is authoritative.

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

## Scheduling

The report generator is intentionally cron-friendly:

```bash
0 7 * * 1 cd /srv/oil-signal && .venv/bin/python examples/generate_weekly_brief.py > /var/reports/oilsignal-weekly.md
```

Managed email/Slack/Teams delivery can plug into the same validated report boundary; the community core does not need a hosted service to generate or inspect the report.

## Repository layout

```text
backend/oilsignal/
├── agent/          # typed tools, validator, optional LLM client
├── alerts/         # transparent threshold rules + delivery protocol
├── analytics/      # deterministic petroleum time-series calculations
├── api/            # FastAPI endpoints
├── data_ingestion/ # EIA abstraction + offline idempotent fixtures
├── reports/        # cited report builders + renderers
└── storage/        # SQLModel metadata
frontend/           # React + TypeScript + Vite
examples/           # offline ingestion and report CLI examples
tests/              # network-free fixtures and acceptance tests
docs/               # architecture, provenance, safety, open-core model
```

## Safety and product boundary

OilSignal v1 is for **operational decision support**. It deliberately excludes order execution, buy/sell recommendations, portfolio sizing, and price prediction. Missing evidence must fail closed or omit a section instead of creating a plausible number. See [`docs/agent-safety.md`](docs/agent-safety.md).

## Open core

Community code is Apache-2.0 with no artificial feature lockouts. A commercial hosted product can charge for reliability, scheduled delivery, organization workspaces, SSO/RBAC, private/vendor data connectors, managed retention, VPC/on-prem deployment, and enterprise support. See [`docs/open-core.md`](docs/open-core.md).

## Roadmap

1. Production EIA petroleum route mappings and normalized live ingestion jobs.
2. More U.S. series: gasoline, jet fuel, imports, implied demand, refinery balances, and PADD-level inventories.
3. Data-release calendar and scheduler with freshness/SLA checks.
4. Configurable multi-signal alerts combining inventory, utilization, and optional customer price data.
5. Evaluation suite for claim coverage, citation accuracy, and explanation faithfulness.
6. Optional private connectors and organization knowledge boundaries.
7. Facility/emissions intelligence module using public EPA data after the fundamentals workflow is mature.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
