from __future__ import annotations

from oilsignal.agent.validation import validate_report
from oilsignal.analytics.crude_balance import (
    COMMERCIAL_CRUDE_STOCKS,
    CRUDE_EXPORTS,
    CRUDE_IMPORTS,
    CRUDE_PRODUCTION,
    CRUDE_REFINERY_INPUT,
    CrudeBalanceSnapshot,
    build_crude_balance,
)
from oilsignal.models import Citation, Claim, ClaimKind, Observation, Report, ReportSection
from oilsignal.reports.weekly import MetricSpec, WeeklyPetroleumBrief


class DistillateSupplyRiskBrief:
    def build(self, observations: list[Observation]) -> Report:
        report = WeeklyPetroleumBrief(
            metrics=(
                MetricSpec("PET.DISTP2.W", "PADD 2 distillate stocks", "Supply risk"),
                MetricSpec(
                    "PET.DISTPSUS.W",
                    "U.S. distillate product supplied",
                    "Demand pressure",
                ),
            )
        ).build(observations)
        report.report_type = "distillate_supply_risk_brief"
        report.title = f"Distillate Supply Risk Brief — {report.as_of.isoformat()}"
        report.metadata["focus"] = "PADD 2 distillate inventory and U.S. product supplied"
        return validate_report(report)


class RefineryUtilizationWatch:
    def build(self, observations: list[Observation]) -> Report:
        report = WeeklyPetroleumBrief(
            metrics=(MetricSpec("PET.UTILUS.W", "U.S. refinery utilization", "Utilization"),)
        ).build(observations)
        report.report_type = "refinery_utilization_watch"
        report.title = f"Refinery Utilization Watch — {report.as_of.isoformat()}"
        report.metadata["focus"] = "U.S. refinery utilization"
        return validate_report(report)


class CrudeBalanceWatch:
    def build(self, observations: list[Observation]) -> Report:
        snapshot = build_crude_balance(observations)
        scoped = [row for row in observations if row.observation_date <= snapshot.as_of]
        report = WeeklyPetroleumBrief(
            metrics=(
                MetricSpec(CRUDE_PRODUCTION, "U.S. crude oil field production", "Production"),
                MetricSpec(CRUDE_IMPORTS, "U.S. crude oil imports", "Imports"),
                MetricSpec(CRUDE_EXPORTS, "U.S. crude oil exports", "Exports"),
                MetricSpec(
                    CRUDE_REFINERY_INPUT,
                    "U.S. refiner net input of crude oil",
                    "Refinery crude input",
                ),
            )
        ).build(scoped)
        report.report_type = "crude_balance_watch"
        report.title = f"Crude Balance Watch — {snapshot.as_of.isoformat()}"
        report.sections.extend(self._balance_sections(observations, snapshot))
        report.metadata.update(
            {
                "focus": "U.S. weekly crude core flows and commercial-stock reconciliation",
                "scope": (
                    "Partial deterministic flow reconciliation; not an official EIA balance "
                    "identity and not a substitute for unmodeled flows or adjustments."
                ),
            }
        )
        return validate_report(report)

    @staticmethod
    def _balance_sections(
        observations: list[Observation],
        snapshot: CrudeBalanceSnapshot,
    ) -> list[ReportSection]:
        core = snapshot.core_flow_balance
        stock = snapshot.stock_change_rate
        residual = snapshot.other_adjustment_residual
        core_claim = Claim(
            text=(
                f"Core crude flow balance was {core.result:+,.1f} {core.unit}, calculated as "
                "production plus imports minus exports and refinery input."
            ),
            kind=ClaimKind.NUMERIC,
            citations=_flow_citations(observations, snapshot.as_of, core.calculation_id),
            calculation=core,
        )
        stock_claim = Claim(
            text=(
                f"Commercial crude stocks changed at an equivalent rate of "
                f"{stock.result:+,.1f} {stock.unit} over "
                f"{snapshot.stock_interval_days} days."
            ),
            kind=ClaimKind.NUMERIC,
            citations=_stock_citations(observations, stock.calculation_id, stock.input_observation_dates),
            calculation=stock,
        )
        residual_claim = Claim(
            text=(
                f"Observed stock change minus the core-flow balance was "
                f"{residual.result:+,.1f} {residual.unit}. This other/adjustment residual "
                "captures flows and statistical adjustments outside the four core inputs, "
                "rather than representing a forecast error."
            ),
            kind=ClaimKind.NUMERIC,
            citations=[
                *_flow_citations(observations, snapshot.as_of, residual.calculation_id),
                *_stock_citations(
                    observations,
                    residual.calculation_id,
                    residual.input_observation_dates,
                ),
            ],
            calculation=residual,
        )
        return [
            ReportSection(heading="Core flow balance", claims=[core_claim]),
            ReportSection(heading="Commercial-stock reconciliation", claims=[stock_claim, residual_claim]),
        ]


def _flow_citations(
    observations: list[Observation],
    observation_date,  # type: ignore[no-untyped-def]
    calculation_id: str,
) -> list[Citation]:
    series_ids = (CRUDE_PRODUCTION, CRUDE_IMPORTS, CRUDE_EXPORTS, CRUDE_REFINERY_INPUT)
    citations: list[Citation] = []
    for series_id in series_ids:
        row = next(
            row
            for row in observations
            if row.series_id == series_id and row.observation_date == observation_date
        )
        citations.append(
            Citation(
                source_url=row.source_url,
                series_id=row.series_id,
                observation_date=row.observation_date,
                calculation_id=calculation_id,
            )
        )
    return citations


def _stock_citations(
    observations: list[Observation],
    calculation_id: str,
    dates,  # type: ignore[no-untyped-def]
) -> list[Citation]:
    citations: list[Citation] = []
    for observation_date in sorted(set(dates)):
        row = next(
            row
            for row in observations
            if row.series_id == COMMERCIAL_CRUDE_STOCKS
            and row.observation_date == observation_date
        )
        citations.append(
            Citation(
                source_url=row.source_url,
                series_id=row.series_id,
                observation_date=row.observation_date,
                calculation_id=calculation_id,
            )
        )
    return citations
