from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel

from oilsignal.analytics.petroleum import SeriesSnapshot


class Operator(StrEnum):
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"


class MetricField(StrEnum):
    CURRENT = "current"
    WEEK_OVER_WEEK = "week_over_week"
    YEAR_OVER_YEAR = "year_over_year"
    ANOMALY_Z_SCORE = "anomaly_z_score"


class ThresholdRule(BaseModel):
    rule_id: str
    series_id: str
    field: MetricField
    operator: Operator
    threshold: float
    message: str

    def evaluate(self, snapshot: SeriesSnapshot) -> AlertEvent | None:
        value = _read_field(snapshot, self.field)
        if value is None or not _compare(value, self.operator, self.threshold):
            return None
        return AlertEvent(
            rule_id=self.rule_id,
            series_id=self.series_id,
            as_of=snapshot.as_of.isoformat(),
            value=value,
            threshold=self.threshold,
            message=self.message,
        )


class AlertEvent(BaseModel):
    rule_id: str
    series_id: str
    as_of: str
    value: float
    threshold: float
    message: str


class DeliveryAdapter(Protocol):
    def send(self, event: AlertEvent) -> None: ...


class ConsoleDelivery:
    def send(self, event: AlertEvent) -> None:
        print(event.model_dump_json())


def _read_field(snapshot: SeriesSnapshot, field: MetricField) -> float | None:
    if field == MetricField.CURRENT:
        return snapshot.current
    if field == MetricField.WEEK_OVER_WEEK:
        return snapshot.week_over_week.result if snapshot.week_over_week else None
    if field == MetricField.YEAR_OVER_YEAR:
        return snapshot.year_over_year.result if snapshot.year_over_year else None
    return snapshot.anomaly_z_score


def _compare(value: float, operator: Operator, threshold: float) -> bool:
    if operator == Operator.LT:
        return value < threshold
    if operator == Operator.LTE:
        return value <= threshold
    if operator == Operator.GT:
        return value > threshold
    return value >= threshold
