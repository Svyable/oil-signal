from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from oilsignal.models import CalculationTrace, Observation

CRUDE_PRODUCTION = "PET.CRPRODUS.W"
CRUDE_IMPORTS = "PET.CRIMUS.W"
CRUDE_EXPORTS = "PET.CREXUS.W"
CRUDE_REFINERY_INPUT = "PET.CRINUS.W"
COMMERCIAL_CRUDE_STOCKS = "PET.CRDUUS.W"
FLOW_SERIES = (
    CRUDE_PRODUCTION,
    CRUDE_IMPORTS,
    CRUDE_EXPORTS,
    CRUDE_REFINERY_INPUT,
)


class CrudeBalanceSnapshot(BaseModel):
    as_of: date
    core_flow_balance: CalculationTrace
    stock_change_rate: CalculationTrace
    other_adjustment_residual: CalculationTrace
    stock_interval_days: int


def build_crude_balance(
    observations: list[Observation],
    *,
    as_of: date | None = None,
) -> CrudeBalanceSnapshot:
    """Build a partial crude-flow reconciliation without implying an official EIA identity."""

    common_dates: set[date] | None = None
    for series_id in FLOW_SERIES:
        dates = {
            row.observation_date
            for row in observations
            if row.series_id == series_id and (as_of is None or row.observation_date <= as_of)
        }
        common_dates = dates if common_dates is None else common_dates & dates
    if not common_dates:
        raise ValueError("crude balance requires aligned production, import, export, and refinery-input data")

    balance_date = max(common_dates)
    flow_rows = {
        series_id: _row_for_date(observations, series_id, balance_date)
        for series_id in FLOW_SERIES
    }
    production = flow_rows[CRUDE_PRODUCTION].value
    imports = flow_rows[CRUDE_IMPORTS].value
    exports = flow_rows[CRUDE_EXPORTS].value
    refinery_input = flow_rows[CRUDE_REFINERY_INPUT].value
    core_result = production + imports - exports - refinery_input
    core_trace = CalculationTrace(
        operation="core_crude_flow_balance",
        expression="production + imports - exports - refinery_input",
        input_series_ids=list(FLOW_SERIES),
        input_observation_dates=[balance_date],
        inputs={
            "production": production,
            "imports": imports,
            "exports": exports,
            "refinery_input": refinery_input,
        },
        result=core_result,
        unit="thousand barrels per day",
    )

    current_stock = _row_for_date(observations, COMMERCIAL_CRUDE_STOCKS, balance_date)
    prior_candidates = sorted(
        (
            row
            for row in observations
            if row.series_id == COMMERCIAL_CRUDE_STOCKS
            and row.observation_date < balance_date
        ),
        key=lambda row: row.observation_date,
    )
    if not prior_candidates:
        raise ValueError("crude balance requires a prior commercial-crude stock observation")
    prior_stock = prior_candidates[-1]
    interval_days = (balance_date - prior_stock.observation_date).days
    if interval_days < 1:
        raise ValueError("commercial-crude stock observations must have increasing dates")

    stock_change_rate = (current_stock.value - prior_stock.value) / interval_days
    stock_trace = CalculationTrace(
        operation="commercial_crude_stock_change_rate",
        expression="(current_stock - prior_stock) / days_between_observations",
        input_series_ids=[COMMERCIAL_CRUDE_STOCKS],
        input_observation_dates=[prior_stock.observation_date, current_stock.observation_date],
        inputs={
            "current_stock": current_stock.value,
            "prior_stock": prior_stock.value,
            "days_between_observations": float(interval_days),
        },
        result=stock_change_rate,
        unit="thousand barrels per day",
    )

    residual = stock_change_rate - core_result
    residual_trace = CalculationTrace(
        operation="crude_other_adjustment_residual",
        expression=(
            "((current_stock - prior_stock) / days_between_observations) "
            "- (production + imports - exports - refinery_input)"
        ),
        input_series_ids=[COMMERCIAL_CRUDE_STOCKS, *FLOW_SERIES],
        input_observation_dates=[prior_stock.observation_date, balance_date],
        inputs={
            "current_stock": current_stock.value,
            "prior_stock": prior_stock.value,
            "days_between_observations": float(interval_days),
            "production": production,
            "imports": imports,
            "exports": exports,
            "refinery_input": refinery_input,
        },
        result=residual,
        unit="thousand barrels per day",
    )

    return CrudeBalanceSnapshot(
        as_of=balance_date,
        core_flow_balance=core_trace,
        stock_change_rate=stock_trace,
        other_adjustment_residual=residual_trace,
        stock_interval_days=interval_days,
    )


def _row_for_date(
    observations: list[Observation],
    series_id: str,
    observation_date: date,
) -> Observation:
    for row in observations:
        if row.series_id == series_id and row.observation_date == observation_date:
            return row
    raise ValueError(f"missing {series_id} observation for {observation_date.isoformat()}")
