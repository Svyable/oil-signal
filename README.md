# OilSignal

> Evidence-first oil-market intelligence for U.S. petroleum fundamentals.

OilSignal is a self-hosted, open-source decision-support system that turns public petroleum data into cited, auditable briefs, inventory alerts, and “what changed?” explanations. It is **not** a trading bot, does not execute trades, and does not provide investment recommendations or price predictions.

## Build plan

1. Define typed data/provenance models and an offline test harness.
2. Add fixture ingestion into Parquet + DuckDB-backed metadata.
3. Add deterministic analytics, citation objects, claim validation, and report rendering.
4. Expose the workflow through FastAPI endpoints and a lightweight React/Vite interface.
5. Package one-command self-hosting with Docker Compose and document the open-core model, safety model, provenance chain, and contributor workflow.

## Target repository tree

```text
.
├── backend/
│   ├── oilsignal/
│   │   ├── agent/
│   │   ├── analytics/
│   │   ├── api/
│   │   ├── data_ingestion/
│   │   ├── reports/
│   │   └── storage/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   ├── Dockerfile
│   └── package.json
├── tests/
│   └── fixtures/
├── examples/
├── docs/
│   ├── architecture.md
│   ├── data-provenance.md
│   ├── open-core.md
│   └── agent-safety.md
├── .github/workflows/ci.yml
├── docker-compose.yml
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
└── LICENSE
```

Implementation is being developed in small commits on a feature branch. The finished README will include exact setup, test, development, and self-hosting commands.
