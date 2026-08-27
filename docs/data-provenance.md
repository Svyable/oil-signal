# Data provenance

OilSignal treats provenance as application data, not a footnote.

## Observation contract

Every normalized observation records:

- `source_url`
- `series_id`
- `observation_date`
- `fetched_at`
- `raw_hash` (SHA-256 of the fetched or fixture payload)
- metric, product, geography, frequency, unit, and value

The normalized record is written to Parquet. The ingestion run is also recorded in the SQLModel metadata database with raw and Parquet paths, status, timestamps, and row count.

## Calculation contract

A `CalculationTrace` records the operation, a human-readable expression, input series IDs, input observation dates, named numeric inputs, result, and unit. This is what makes a sentence such as “stocks fell week over week” reproducible instead of merely plausible.

## Citation contract

A `Citation` names the source, source URL, series ID, observation date, and calculation ID when the claim depends on a derived calculation. Renderers preserve that citation object in JSON and surface it in Markdown/HTML output.

## Idempotency

Fixture ingestion keys each run by the SHA-256 hash of the raw file. Re-ingesting the same payload reuses the existing normalized artifact instead of duplicating rows. Live connectors should follow the same content-hash or source-version strategy.

## Production guidance

For live EIA data, retain the raw response alongside normalized Parquet, pin the route/facet configuration used by the run, and avoid silently rewriting historical observations. Corrections should create a new ingestion run with a new fetch timestamp and hash.
