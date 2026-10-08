# OilSignal founding-pilot proof annex — fixture demonstration

**Status (2026-10-08): DEMONSTRATION ONLY — NOT LIVE EIA DATA, NOT A CLIENT DELIVERABLE.** This is a manually checked example assembled from the repository's synthetic test fixture, **not** a captured production OilSignal report. It is intended to show a buyer exactly what a source-checkable weekly annex could contain. Do not quote its values as petroleum-market facts.

## One-screen specimen: U.S. petroleum evidence, fixture week ending 2026-08-21

| Observation | 2026-08-14 | 2026-08-21 | Change | Evidence location |
| --- | ---: | ---: | ---: | --- |
| PADD 2 distillate stocks (thousand barrels) | 27,600 | 26,900 | **−700 thousand barrels (−2.54%)** | [Synthetic fixture, `PET.DISTP2.W`](../tests/fixtures/petroleum_weekly.csv) |
| U.S. refinery utilization (percent) | 91.9 | 90.8 | **−1.1 percentage points** | [Synthetic fixture, `PET.UTILUS.W`](../tests/fixtures/petroleum_weekly.csv) |
| U.S. crude stocks (thousand barrels) | 416,700 | 418,200 | **+1,500 thousand barrels (+0.36%)** | [Synthetic fixture, `PET.CRDUUS.W`](../tests/fixtures/petroleum_weekly.csv) |

**Calculation trace:** current minus prior observation; relative percentage = (current − prior) / prior × 100; refinery utilization is expressed as a percentage-*point* change, not a relative percent change. Numbers are rounded only for display. These fixture identifiers are development-only `PET.*` identifiers, not maintained live EIA series.

**Permissible descriptive statement:** “In this synthetic example, PADD 2 distillate inventory is 700 thousand barrels lower week over week while refinery utilization is 1.1 percentage points lower.”

**Not permissible:** “The Midwest is short diesel,” “diesel prices will rise,” “the EIA reported these values,” or any claim that the two series prove causality. The fixture does not establish any such conclusion.

**Human review field:** [ ] values checked against the cited source; [ ] units and week alignment checked; [ ] material claims traced; [ ] freshness/provenance checked; [ ] suitable for the intended audience. An unchecked specimen is not publication-ready.

## Actual live-production proof requirements

For a real pilot week, substitute **only** a successfully ingested, verified live EIA registry; do not copy the specimen's numbers. Use the existing product, not a new data pipeline:

1. Verify registry: `oilsignal eia-verify-registry --registry examples/eia-series.example.json`.
2. Ingest current observations: `oilsignal ingest-eia --registry examples/eia-series.example.json --data-dir ./data`.
3. Require `oilsignal freshness --data-dir ./data` to pass before reporting or fulfillment.
4. Generate the buyer-selected existing report: `oilsignal report --type crude-balance --format markdown --data-dir ./data` for a crude analyst, or the existing distillate/weekly product for a downstream buyer.
5. Inspect numeric claims, observation dates, units, citations, calculation traces, source hashes, and any residual/limitations. Never present the partial crude reconciliation as an official EIA balance identity.
6. Retain report output and, where used, the evidence-pack `evidence_sha256`, fulfillment audit ID, release date, and reviewer sign-off. Do not claim a digest or audit ID exists until actually generated.

**Release-calendar stress test:** As checked on 2026-10-08, the [official EIA WPSR schedule](https://www.eia.gov/petroleum/supply/weekly/schedule.php) moves the report for the week ending **2026-10-09** to **Thursday 2026-10-15 at noon Eastern** (Columbus Day exception). The demo must not assume Wednesday 10:30 a.m. for that cycle. Test that no stale or not-yet-released data is passed off as current. Recheck the official calendar before the cycle; the schedule can change.

## Commercial proof, not just technical proof

**Candidate buyer:** petroleum consultant or small research team with a named analyst who already produces a weekly client/internal petroleum note. **Price hypothesis:** $1,500 fixed for four consecutive weekly release cycles; potential continuation at $750/month only after value is demonstrated. **Alternative:** free EIA releases + spreadsheets/scripts or an existing research platform.

Ask the buyer for **one existing recurring question** and a redacted version of its current output. Measure the same four cycles in parallel. The buying case fails if the buyer does not use weekly EIA data, has negligible manual effort, cannot approve a pilot, or would need custom inputs that are not in the current maintained registry.

| Pilot measure | Baseline (buyer workflow) | OilSignal parallel workflow |
| --- | --- | --- |
| Release-to-review-ready minutes | Not measured | Not measured |
| Human analyst minutes per cycle | Not measured | Not measured |
| Manual source lookups | Not measured | Not measured |
| Claims with traceable source and calculation | Not measured | Not measured |
| Corrections/rechecks and stale-output blocks | Not measured | Not measured |
| Buyer says usable in existing deliverable? | Not measured | Not measured |

**Pass gate:** at least 3 substantive conversations and 1 explicit $1,500 pilot acceptance or concrete procurement/invoice step among 10 genuinely qualified accounts. Research-only names are not qualified. No paid customer, savings, or conversion is claimed by this specimen.

**Engineering decision:** no new features, billing, connector, or account system until the commercial gate passes. Existing deterministic analytics, cited SKUs, freshness controls, founding-pilot entitlement, and fulfillment audit are the product. See [buyer-validation kit](founding-pilot-buyer-validation-kit.md) on the commercial experiment branch and [founding-pilot operating guide](founding-pilot.md).
