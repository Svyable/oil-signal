from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from oilsignal.analytics.petroleum import SeriesSnapshot, build_snapshot
from oilsignal.models import Observation, Report
from oilsignal.reports.renderers import render_report
from oilsignal.reports.weekly import WeeklyPetroleumBrief


class GetSeriesInput(BaseModel):
    series_id: str
    as_of: date | None = None


class RenderBriefInput(BaseModel):
    format: str = "markdown"


def get_series(observations: list[Observation], request: GetSeriesInput) -> list[Observation]:
    return sorted(
        [
            row
            for row in observations
            if row.series_id == request.series_id
            and (request.as_of is None or row.observation_date <= request.as_of)
        ],
        key=lambda row: row.observation_date,
    )


def calculate_inventory_change(
    observations: list[Observation], request: GetSeriesInput
) -> SeriesSnapshot:
    return build_snapshot(observations, request.series_id, request.as_of)


def compare_seasonal_range(
    observations: list[Observation], request: GetSeriesInput
) -> SeriesSnapshot:
    return build_snapshot(observations, request.series_id, request.as_of)


def build_weekly_brief(observations: list[Observation]) -> Report:
    return WeeklyPetroleumBrief().build(observations)


def render_brief(report: Report, request: RenderBriefInput) -> str:
    return render_report(report, request.format)
