# EIA API setup

OilSignal keeps EIA route selection data-driven. The EIA API is self-describing, and route/facet definitions can change, so market-series mappings live in a registry rather than being buried inside analytics code.

The repository includes a core weekly petroleum registry in `examples/eia-series.example.json`, last verified against EIA public documentation/series pages on **2026-08-26**. It uses EIA API v2's documented `/seriesid/<legacy-series-id>` compatibility route to resolve one legacy weekly series per canonical OilSignal ID without ambiguous facets.

EIA API v2 documentation: https://www.eia.gov/opendata/documentation.php

## 1. Configure a key

Request a free EIA API key, then either copy `.env.example` to `.env` or export:

```bash
export OILSIGNAL_EIA_API_KEY=your-key
```

Tests, fixture ingestion, and deterministic reports over already-ingested data do not require a key.

## 2. Ingest the verified core registry

```bash
oilsignal ingest-eia --registry examples/eia-series.example.json --data-dir ./data
```

The current core mappings are:

| OilSignal canonical ID | EIA legacy weekly series | Meaning |
| --- | --- | --- |
| `PET.CRDUUS.W` | `PET.WCESTUS1.W` | U.S. commercial crude stocks excluding SPR |
| `PET.GASUS.W` | `PET.WGTSTUS1.W` | U.S. total gasoline stocks |
| `PET.DISTUS.W` | `PET.WDISTUS1.W` | U.S. distillate fuel oil stocks |
| `PET.DISTP2.W` | `PET.WDISTP21.W` | PADD 2 distillate fuel oil stocks |
| `PET.JETUS.W` | `PET.WKJSTUS1.W` | U.S. kerosene-type jet fuel stocks |
| `PET.UTILUS.W` | `PET.WPULEUS3.W` | U.S. refinery utilization |
| `PET.CRIMUS.W` | `PET.WCRIMUS2.W` | U.S. crude oil imports |

Canonical IDs are OilSignal's stable internal contract. EIA route identifiers remain registry data so they can be re-verified or replaced without rewriting report logic.

## 3. Discover or re-verify routes

Inspect route metadata before adding a new production series:

```bash
oilsignal eia-metadata --route petroleum/sum/sndw
```

If the route advertises a facet, inspect its allowed values:

```bash
oilsignal eia-metadata --route petroleum/sum/sndw --facet <facet-id>
```

EIA v2 limits JSON responses to 5,000 rows. OilSignal deliberately fails ingestion if `response.total` exceeds the returned row count; constrain dates and facets instead of silently accepting a truncated dataset.

## 4. Build or extend a registry

Copy `examples/eia-series.example.json` and define one `SeriesSpec` per canonical OilSignal series. Each spec provides:

- a stable `canonical_series_id` used by analytics and citations;
- metric, product, geography, and unit normalization;
- the EIA route, frequency, requested data column, date bounds, and facets;
- the response fields containing the observation period and numeric value.

A spec must resolve to at most one observation per canonical series and period. If EIA returns duplicate periods, OilSignal rejects the run as under-constrained rather than guessing which facet row is correct.

## 5. Provenance written by ingestion

Each live run stores:

- raw EIA JSON per configured series;
- SHA-256 hashes of those raw payloads on every normalized observation;
- normalized Parquet data;
- SQLModel ingestion-run metadata with `source = eia:v2`;
- citation URLs that identify the public EIA dataset route without exposing the API key.

If the same registry and source payloads are seen again, the normalized dataset is reused deterministically.

## 6. Check freshness before publishing intelligence

```bash
oilsignal freshness --data-dir ./data
```

For live `eia:v2` ingestion runs, OilSignal compares weekly observations with EIA's WPSR release schedule and waits through EIA's documented two-hour API availability grace window. Once a new week is expected, a lagging live series makes readiness/report/Q&A/alert paths fail closed until current data arrives.

The offline fixture has different ingestion provenance and is intentionally exempt from the live release gate. See `docs/freshness.md` for timing and holiday behavior.

## 7. Render a report

```bash
oilsignal report --type weekly --format markdown --data-dir ./data
```

Live data uses the same `Observation`, calculation trace, claim validator, and report code paths as the offline fixtures; the difference is that live evidence must also pass the release-aware freshness contract.
