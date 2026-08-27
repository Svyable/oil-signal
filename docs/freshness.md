# Live-data freshness and WPSR release gating

OilSignal treats **freshness as part of evidence validity**, not as a dashboard decoration. A live petroleum report that silently presents last week's data after a new release is expected is operationally misleading even if every number is correctly cited.

## Authoritative timing sources

The weekly gate is based on EIA's public Weekly Petroleum Status Report schedule and EIA's API guidance:

- WPSR release schedule: https://www.eia.gov/petroleum/supply/weekly/schedule.php
- EIA API FAQ: https://www.eia.gov/opendata/faqs.php

The normal WPSR publication time is Wednesday at 10:30 a.m. U.S. Eastern Time. EIA notes that API data can become available up to two hours after publication, so OilSignal adds a two-hour API grace window before requiring the newly released week.

## Expected week-ending logic

Weekly petroleum observations are keyed to a Friday week-ending date. For a standard week:

1. the Friday closes the reporting week;
2. WPSR is scheduled five days later, Wednesday at 10:30 a.m. Eastern;
3. OilSignal waits through the two-hour API grace window;
4. after that boundary, the latest live series must cover that Friday or a later observation date.

Before the boundary, OilSignal continues to accept the previous expected week so it does not flag the source as stale while EIA is still inside its documented publication/API window.

## 2026 holiday overrides

The default calendar encodes the delayed 2026 WPSR releases published by EIA for these week-ending dates:

| Week ending | Scheduled release |
| --- | --- |
| 2026-01-16 | 2026-01-22 12:00 ET |
| 2026-02-13 | 2026-02-19 12:00 ET |
| 2026-05-22 | 2026-05-28 12:00 ET |
| 2026-09-04 | 2026-09-10 12:00 ET |
| 2026-10-09 | 2026-10-15 12:00 ET |
| 2026-11-06 | 2026-11-12 12:00 ET |

These values are code, not an eternal assumption. Maintainers should compare them with EIA's published schedule when rolling the calendar into a new year.

## Provenance determines whether the gate applies

OilSignal does not infer "live" merely from a URL. The latest Parquet dataset is associated with its SQLModel ingestion-run metadata:

- `source = eia:v2` → live EIA freshness gate applies;
- fixture/demo ingestion → freshness is `not_applicable`.

This distinction is intentional because offline fixtures may use EIA-shaped URLs to test citation behavior. Test data must never accidentally become "current" just because a hostname resembles the live source.

## Fail-closed behavior

For a live EIA dataset, OilSignal calculates the latest observation date per weekly series. If **any** live weekly series trails the expected week-ending date, freshness is `stale` and identifies the lagging series IDs.

The gate is used by:

- `GET /health/ready`, which returns HTTP 503 for stale live evidence;
- report endpoints and CLI rendering;
- deterministic Q&A;
- stateless and stateful alert evaluation.

This prevents stale evidence from creating a fresh-looking report, answer, or notification.

## CLI

Inspect freshness directly:

```bash
oilsignal freshness --data-dir ./data
```

The command prints structured JSON and exits with status `2` when live data is stale. A fixture-backed dataset returns `not_applicable` and exits successfully.

## Scope

The current policy is intentionally WPSR-oriented and only evaluates weekly EIA observations. Monthly, daily, or future public-data modules need their own release calendars and freshness contracts rather than reusing WPSR timing by analogy.
