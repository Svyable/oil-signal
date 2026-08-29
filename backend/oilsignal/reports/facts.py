from __future__ import annotations

from dataclasses import dataclass

from oilsignal.agent.validation import validate_report
from oilsignal.analytics.petroleum import build_snapshot
from oilsignal.models import Citation, Claim, ClaimKind, Observation, Report, ReportSection


@dataclass(frozen=True)
class FactProductSpec:
    sku: str
    series_id: str
    name: str
    description: str
    label: str
    demand_proxy: bool = False


FACT_PRODUCT_SPECS = (
    FactProductSpec(
        sku="fact-us-crude-stocks",
        series_id="PET.CRDUUS.W",
        name="U.S. Commercial Crude Stocks Fact",
        description="Latest U.S. commercial crude stocks excluding SPR plus deterministic week-over-week change.",
        label="U.S. commercial crude stocks excluding SPR",
    ),
    FactProductSpec(
        sku="fact-us-gasoline-stocks",
        series_id="PET.GASUS.W",
        name="U.S. Gasoline Stocks Fact",
        description="Latest U.S. total gasoline stocks plus deterministic week-over-week change.",
        label="U.S. total gasoline stocks",
    ),
    FactProductSpec(
        sku="fact-us-distillate-stocks",
        series_id="PET.DISTUS.W",
        name="U.S. Distillate Stocks Fact",
        description="Latest U.S. distillate fuel-oil stocks plus deterministic week-over-week change.",
        label="U.S. distillate fuel-oil stocks",
    ),
    FactProductSpec(
        sku="fact-padd2-distillate-stocks",
        series_id="PET.DISTP2.W",
        name="PADD 2 Distillate Stocks Fact",
        description="Latest PADD 2 distillate fuel-oil stocks plus deterministic week-over-week change.",
        label="PADD 2 distillate fuel-oil stocks",
    ),
    FactProductSpec(
        sku="fact-us-jet-fuel-stocks",
        series_id="PET.JETUS.W",
        name="U.S. Jet Fuel Stocks Fact",
        description="Latest U.S. kerosene-type jet-fuel stocks plus deterministic week-over-week change.",
        label="U.S. kerosene-type jet-fuel stocks",
    ),
    FactProductSpec(
        sku="fact-us-refinery-utilization",
        series_id="PET.UTILUS.W",
        name="U.S. Refinery Utilization Fact",
        description="Latest U.S. refinery utilization plus deterministic week-over-week change.",
        label="U.S. refinery utilization",
    ),
    FactProductSpec(
        sku="fact-us-crude-imports",
        series_id="PET.CRIMUS.W",
        name="U.S. Crude Imports Fact",
        description="Latest U.S. crude-oil imports plus deterministic week-over-week change.",
        label="U.S. crude-oil imports",
    ),
    FactProductSpec(
        sku="fact-us-crude-production",
        series_id="PET.CRPRODUS.W",
        name="U.S. Crude Production Fact",
        description="Latest U.S. crude-oil field production plus deterministic week-over-week change.",
        label="U.S. crude-oil field production",
    ),
    FactProductSpec(
        sku="fact-us-crude-exports",
        series_id="PET.CREXUS.W",
        name="U.S. Crude Exports Fact",
        description="Latest U.S. crude-oil exports plus deterministic week-over-week change.",
        label="U.S. crude-oil exports",
    ),
    FactProductSpec(
        sku="fact-us-crude-refinery-input",
        series_id="PET.CRINUS.W",
        name="U.S. Crude Refinery Input Fact",
        description="Latest U.S. refiner net input of crude oil plus deterministic week-over-week change.",
        label="U.S. refiner net input of crude oil",
    ),
    FactProductSpec(
        sku="fact-us-gasoline-product-supplied",
        series_id="PET.GASPSUS.W",
        name="U.S. Gasoline Product Supplied Fact",
        description="Latest U.S. finished motor gasoline product supplied, a demand proxy, plus week-over-week change.",
        label="U.S. finished motor gasoline product supplied",
        demand_proxy=True,
    ),
    FactProductSpec(
        sku="fact-us-distillate-product-supplied",
        series_id="PET.DISTPSUS.W",
        name="U.S. Distillate Product Supplied Fact",
        description="Latest U.S. distillate product supplied, a demand proxy, plus week-over-week change.",
        label="U.S. distillate product supplied",
        demand_proxy=True,
    ),
    FactProductSpec(
        sku="fact-us-jet-product-supplied",
        series_id="PET.JETPSUS.W",
        name="U.S. Jet Fuel Product Supplied Fact",
        description="Latest U.S. jet-fuel product supplied, a demand proxy, plus week-over-week change.",
        label="U.S. jet-fuel product supplied",
        demand_proxy=True,
    ),
    FactProductSpec(
        sku="fact-us-total-products-supplied",
        series_id="PET.TOTALPSUS.W",
        name="U.S. Total Products Supplied Fact",
        description="Latest U.S. petroleum products supplied, a demand proxy, plus week-over-week change.",
        label="U.S. petroleum products supplied",
        demand_proxy=True,
    ),
)


class SeriesFactBrief:
    """Small deterministic report for one maintained petroleum series."""

    def __init__(self, spec: FactProductSpec) -> None:
        self.spec = spec

    def build(self, observations: list[Observation]) -> Report:
        rows = sorted(
            [row for row in observations if row.series_id == self.spec.series_id],
            key=lambda row: row.observation_date,
        )
        if not rows:
            raise ValueError(f"no observations found for series {self.spec.series_id}")

        snapshot = build_snapshot(rows, self.spec.series_id)
        current = rows[-1]
        display_label = (
            f"{self.spec.label} (demand proxy)" if self.spec.demand_proxy else self.spec.label
        )
        current_claim = Claim(
            text=(
                f"{display_label} stood at {snapshot.current:,.1f} {snapshot.unit} as of "
                f"{snapshot.as_of.isoformat()}."
            ),
            kind=ClaimKind.NUMERIC,
            citations=[_citation(current)],
        )
        claims = [current_claim]

        if snapshot.week_over_week is not None:
            trace = snapshot.week_over_week
            prior_date = min(trace.input_observation_dates)
            prior = next(row for row in rows if row.observation_date == prior_date)
            claims.append(
                Claim(
                    text=(
                        f"Week-over-week change in {display_label} was "
                        f"{trace.result:+,.1f} {trace.unit}."
                    ),
                    kind=ClaimKind.NUMERIC,
                    citations=[
                        _citation(prior, trace.calculation_id),
                        _citation(current, trace.calculation_id),
                    ],
                    calculation=trace,
                )
            )

        metadata: dict[str, object] = {
            "product_kind": "single_series_fact",
            "series_id": self.spec.series_id,
            "focus": self.spec.label,
        }
        if self.spec.demand_proxy:
            metadata["methodology_note"] = (
                "EIA product supplied is used as a demand proxy and is not a direct measure "
                "of end-use consumption."
            )

        report = Report(
            report_type="series_fact",
            title=f"{self.spec.name} — {snapshot.as_of.isoformat()}",
            as_of=snapshot.as_of,
            sections=[ReportSection(heading="Latest verified fact", claims=claims)],
            metadata=metadata,
        )
        return validate_report(report)


def _citation(row: Observation, calculation_id: str | None = None) -> Citation:
    return Citation(
        source_url=row.source_url,
        series_id=row.series_id,
        observation_date=row.observation_date,
        calculation_id=calculation_id,
    )
