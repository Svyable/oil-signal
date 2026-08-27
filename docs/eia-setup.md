# EIA API setup and maintained registry verification

OilSignal keeps EIA route selection data-driven. EIA route/facet definitions can change, so source mappings live in a registry rather than being buried inside analytics code.

The repository includes a maintained weekly petroleum registry at `examples/eia-series.example.json`, with explicit `verified_at` metadata. It uses EIA API v2's documented `/seriesid/<legacy-series-id>` compatibility route to resolve one legacy weekly series per canonical OilSignal ID without ambiguous facets.

EIA API v2 documentation: https://www.eia.gov/opendata/documentation.php

## 1. Configure a key

Request a free EIA API key, then either copy `.env.example` to `.env` or export:

```bash
export OILSIGNAL_EIA_API_KEY=your-key
```

Tests, fixture ingestion, and deterministic reports over already-ingested data do not require a key.

## 2. Maintained core registry

The current registry includes inventory, refinery/import, and product-supplied demand-proxy series:

| OilSignal canonical ID | EIA legacy weekly series | Meaning |
| --- | --- | --- |
| `PET.CRDUUS.W` | `PET.WCESTUS1.W` | U.S. commercial crude stocks excluding SPR |
| `PET.GASUS.W` | `PET.WGTSTUS1.W` | U.S. total gasoline stocks |
| `PET.DISTUS.W` | `PET.WDISTUS1.W` | U.S. distillate fuel oil stocks |
| `PET.DISTP2.W` | `PET.WDISTP21.W` | PADD 2 distillate fuel oil stocks |
| `PET.JETUS.W` | `PET.WKJSTUS1.W` | U.S. kerosene-type jet fuel stocks |
| `PET.UTILUS.W` | `PET.WPULEUS3.W` | U.S. refinery utilization |
| `PET.CRIMUS.W` | `PET.WCRIMUS2.W` | U.S. crude oil imports |
| `PET.GASPSUS.W` | `PET.WGFUPUS2.W` | U.S. finished motor gasoline product supplied |
| `PET.DISTPSUS.W` | `PET.WDIUPUS2.W` | U.S. distillate fuel oil product supplied |
| `PET.JETPSUS.W` | `PET.WKJUPUS2.W` | U.S. kerosene-type jet fuel product supplied |
| `PET.TOTALPSUS.W` | `PET.WRPUPUS2.W` | U.S. petroleum products supplied |

Canonical IDs are OilSignal's stable internal contract. EIA identifiers remain registry data so they can be re-verified or replaced without rewriting analytics/report logic.

## 3. Verify the live source contract

Before relying on maintained mappings, probe them directly:

```bash
oilsignal eia-verify-registry --registry examples/eia-series.example.json
```

The verifier checks every configured route independently and reports all failures rather than stopping at the first one. It validates:

- the route returns a response/data list;
- sampled periods parse at the declared frequency and are not duplicated;
- sampled values are present and numeric;
- any returned response frequency matches the registry;
- API version and warning metadata are captured for audit;
- series tagged `release_family: wpsr` cover the currently expected WPSR week.

For a route/shape audit during an EIA publication delay, omit the recency requirement:

```bash
oilsignal eia-verify-registry \
  --registry examples/eia-series.example.json \
  --skip-freshness
```

The command exits `0` only when every series passes and `2` when any source contract fails.

The repository also includes `.github/workflows/eia-registry-verify.yml`, scheduled Friday at 18:00 UTC and manually dispatchable. Set repository secret `EIA_API_KEY` to activate its live probe. Without the secret, the job emits a notice and skips network verification rather than pretending a live check occurred.

## 4. Ingest the verified registry

```bash
oilsignal ingest-eia --registry examples/eia-series.example.json --data-dir ./data
```

Each live run stores raw EIA JSON per configured series, SHA-256 source hashes on normalized observations, Parquet output, SQLModel ingestion-run metadata with `source = eia:v2`, and citation URLs that do not expose the API key.

If the same registry and source payloads are seen again, the normalized dataset is reused deterministically.

## 5. Discover or add routes

Inspect route metadata before adding a new production series:

```bash
oilsignal eia-metadata --route petroleum/sum/sndw
```

If a route advertises a facet, inspect its values:

```bash
oilsignal eia-metadata --route petroleum/sum/sndw --facet <facet-id>
```

EIA v2 limits JSON responses to 5,000 rows. OilSignal fails ingestion if `response.total` exceeds the returned row count; constrain dates/facets rather than silently accepting truncated history.

A custom `SeriesSpec` defines canonical ID, metric/product/geography/unit normalization, EIA route/frequency/data/facets, response period/value fields, and optional `release_family`. A spec must resolve to at most one row per canonical series and period. Duplicate periods fail closed as an under-constrained registry.

## 6. Check ingested-data freshness

```bash
oilsignal freshness --data-dir ./data
```

For live `eia:v2` ingestion runs, OilSignal compares weekly observations with the WPSR release schedule and waits through EIA's documented two-hour API availability grace window. Once a new week is expected, a lagging live series makes readiness/report/Q&A/alert paths fail closed until current data arrives.

The offline fixture has different ingestion provenance and is intentionally exempt from the live release gate. See `docs/freshness.md` for timing and holiday behavior.

## 7. Render a report

```bash
oilsignal report --type weekly --format markdown --data-dir ./data
```

The Weekly Petroleum Brief opportunistically includes maintained inventory, imports, refinery utilization, and product-supplied signals when available. The Distillate Supply Risk Brief adds U.S. distillate product supplied as a demand-pressure section when that series is present. Every numeric claim remains cited through the same validator/calculation path.
