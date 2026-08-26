from __future__ import annotations

from datetime import date, timedelta
from statistics import fmean, pstdev

from pydantic import BaseModel

from oilsignal.models import CalculationTrace, Observation


class SeriesSnapshot(BaseModel):
    series_id: str
    as_of: date
    current: float
    unit: str
    week_over_week: CalculationTrace | None
    four_week_average: CalculationTrace | None
    year_over_year: CalculationTrace | None
    seasonal_low: float | None = None
    seasonal_high: float | None = None
    anomaly_z_score: float | None = None


def _trace(operation: str, expression: str, rows: list[Observation], inputs: dict[str, float], result: float) -> CalculationTrace:
    return CalculationTrace(
        operation=operation,
        expression=expression,
        input_series_ids=sorted({row.series_id for row in rows}),
        input_observation_dates=[row.observation_date for row in rows],
        inputs=inputs,
        result=result,
        unit=rows[-1].unit,
    )


def _year_ago(rows: list[Observation], as_of: date) -> Observation | None:
    target = as_of - timedelta(days=365)
    candidates = [row for row in rows if 350 <= (as_of - row.observation_date).days <= 380]
    return min(candidates, key=lambda row: abs((row.observation_date - target).days), default=None)


def build_snapshot(observations: list[Observation], series_id: str, as_of: date | None = None) -> SeriesSnapshot:
    rows = sorted(
        [row for row in observations if row.series_id == series_id and (as_of is None or row.observation_date <= as_of)],
        key=lambda row: row.observation_date,
    )
    if not rows:
        raise ValueError(f"no observations found for series {series_id}")

    current = rows[-1]
    prior = rows[-2] if len(rows) > 1 else None
    wow = None
    if prior:
        result = current.value - prior.value
        wow = _trace(
            "week_over_week",
            "current - prior",
            [prior, current],
            {"current": current.value, "prior": prior.value},
            result,
        )

    recent = rows[-4:]
    avg = None
    if recent:
        result = fmean(row.value for row in recent)
        avg = _trace(
            "four_week_average",
            "mean(last up to 4 observations)",
            recent,
            {f"value_{index + 1}": row.value for index, row in enumerate(recent)},
            result,
        )

    previous_year = _year_ago(rows[:-1], current.observation_date)
    yoy = None
    if previous_year:
        result = current.value - previous_year.value
        yoy = _trace(
            "year_over_year",
            "current - closest observation ~52 weeks earlier",
            [previous_year, current],
            {"current": current.value, "year_ago": previous_year.value},
            result,
        )

    iso_week = current.observation_date.isocalendar().week
    seasonal = [
        row.value
        for row in rows[:-1]
        if row.observation_date.year < current.observation_date.year
        and abs(row.observation_date.isocalendar().week - iso_week) <= 2
    ]

    history = [row.value for row in rows[:-1][-12:]]
    z_score = None
    if len(history) >= 4:
        sigma = pstdev(history)
        if sigma > 0:
            z_score = (current.value - fmean(history)) / sigma

    return SeriesSnapshot(
        series_id=series_id,
        as_of=current.observation_date,
        current=current.value,
        unit=current.unit,
        week_over_week=wow,
        four_week_average=avg,
        year_over_year=yoy,
        seasonal_low=min(seasonal) if seasonal else None,
        seasonal_high=max(seasonal) if seasonal else None,
        anomaly_z_score=z_score,
    )
