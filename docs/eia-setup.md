# EIA API setup

OilSignal keeps EIA route selection data-driven. The EIA API is self-describing, and route/facet definitions can change, so the repository does not bury market-series mappings inside application code.

## 1. Configure a key

Request a free EIA API key, then either copy `.env.example` to `.env` or export:

```bash
export OILSIGNAL_EIA_API_KEY=your-key
```

Tests, fixture ingestion, and deterministic reports over already-ingested data do not require a key.

## 2. Discover the current route

Inspect route metadata before creating a production registry:

```bash
oilsignal eia-metadata --route petroleum/sum/sndw
```

If the route advertises a facet, inspect its allowed values:

```bash
oilsignal eia-metadata --route petroleum/sum/sndw --facet <facet-id>
```

EIA v2 limits JSON responses to 5,000 rows. OilSignal deliberately fails ingestion if `response.total` exceeds the returned row count; constrain dates and facets instead of silently accepting a truncated dataset.

## 3. Build a registry

Copy `examples/eia-series.example.json` and define one `SeriesSpec` per canonical OilSignal series. Each spec provides:

- a stable `canonical_series_id` used by analytics and citations;
- metric, product, geography, and unit normalization;
- the EIA route, frequency, requested data column, date bounds, and facets;
- the response fields containing the observation period and numeric value.

A spec must resolve to at most one observation per canonical series and period. If EIA returns duplicate periods, OilSignal rejects the run as under-constrained rather than guessing which facet row is correct.

## 4. Ingest

```bash
oilsignal ingest-eia --registry ./my-eia-series.json --data-dir ./data
```

The ingestion run stores:

- raw EIA JSON per configured series;
- SHA-256 hashes of those raw payloads on every normalized observation;
- normalized Parquet data;
- SQLModel ingestion-run metadata;
- citation URLs that identify the public EIA dataset route without exposing the API key.

If the same registry and source payloads are seen again, the normalized dataset is reused deterministically.

## 5. Render a report

```bash
oilsignal report --type weekly --format markdown --data-dir ./data
```

Live data uses the same `Observation`, calculation trace, claim validator, and report code paths as the offline fixtures.
