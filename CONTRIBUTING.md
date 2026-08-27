# Contributing

Thanks for improving OilSignal. Contributions should preserve the evidence-first boundary: raw public data becomes typed observations, deterministic calculations become traces, and narrative claims must cite those traces/observations.

## Development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e "./backend[dev]"
pytest
ruff check backend tests examples
mypy backend/oilsignal
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Run `pre-commit install` once to enable local checks.

## Pull requests

Keep changes narrow, include offline tests for calculations or ingestion behavior, and document any new data source's provenance fields. Do not add proprietary datasets, scraped publisher content, trading execution, price predictions, or hardcoded current-market claims to fixtures.
