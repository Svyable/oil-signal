# Crude Balance Watch

OilSignal's Crude Balance Watch is a deterministic **partial flow reconciliation** for weekly U.S. crude fundamentals. It is designed to help an operator see whether the largest published crude inflows and outflows are directionally consistent with the observed change in commercial crude inventories.

It is **not** an official EIA crude-balance identity, a price model, or a forecast.

## Maintained source series

The maintained weekly registry uses these public EIA series:

| OilSignal ID | EIA weekly series | Meaning | Unit |
| --- | --- | --- | --- |
| `PET.CRPRODUS.W` | `PET.WCRFPUS2.W` | U.S. field production of crude oil | thousand barrels/day |
| `PET.CRIMUS.W` | `PET.WCRIMUS2.W` | U.S. crude oil imports | thousand barrels/day |
| `PET.CREXUS.W` | `PET.WCREXUS2.W` | U.S. crude oil exports | thousand barrels/day |
| `PET.CRINUS.W` | `PET.WCRRIUS2.W` | U.S. refiner net input of crude oil | thousand barrels/day |
| `PET.CRDUUS.W` | `PET.WCESTUS1.W` | U.S. commercial crude stocks excluding SPR | thousand barrels |

All maintained entries are tagged `release_family: wpsr`, so live source verification and production freshness checks use the same WPSR release-calendar contract as other weekly OilSignal intelligence.

## Core-flow balance

For one aligned observation week, OilSignal calculates:

```text
core flow balance = production + imports - exports - refinery input
```

The result is expressed in thousand barrels per day. Positive values mean the four listed core flows provide more inflow than refinery/export outflow; negative values mean the listed outflows exceed the listed inflows.

The calculation requires all four flow series to have an observation on the **same date**. OilSignal fails closed if it cannot find an aligned week rather than mixing publication periods.

## Commercial-stock change rate

Commercial crude stocks are reported in thousand barrels. OilSignal converts the change between the current aligned stock observation and the immediately prior stock observation into a daily-equivalent rate:

```text
stock change rate = (current commercial stocks - prior commercial stocks) / days between observations
```

The actual number of elapsed days is used instead of silently assuming seven days. This makes a data gap visible in the calculation trace.

## Other/adjustment residual

OilSignal then calculates:

```text
other/adjustment residual = stock change rate - core flow balance
```

This residual deliberately has a neutral name. The four core flows are not a complete accounting identity. The difference can reflect flows, transfers, adjustments, timing effects, or other balance components that are not represented by the four maintained inputs.

Do **not** interpret the residual as:

- a forecast error;
- proof that an EIA series is wrong;
- an automatically actionable trading signal;
- a substitute for a complete petroleum supply disposition table.

The useful question is narrower: "How much of the observed commercial-stock movement is left after reconciling the largest maintained weekly crude flows?"

## Evidence contract

The Crude Balance Watch emits separate `CalculationTrace` objects for:

1. core-flow balance;
2. commercial-stock change rate;
3. other/adjustment residual.

Every numeric claim carries citations to the source observations used by its calculation and links those citations to the exact `calculation_id`. The claim validator therefore applies to derived balance claims just as it does to direct inventory or utilization claims.

## CLI and API

Render the report after live registry verification, ingestion, and freshness checks:

```bash
oilsignal report --type crude-balance --format markdown --data-dir ./data
```

The FastAPI endpoint is:

```text
GET /api/reports/crude-balance
```

Deterministic Q&A also recognizes explicit crude production, crude export, refinery-input, and crude-balance questions. A crude-balance answer states that the calculation is a partial reconciliation rather than an official EIA identity.
