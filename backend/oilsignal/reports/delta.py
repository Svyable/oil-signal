from __future__ import annotations

from oilsignal.agent.validation import validate_report
from oilsignal.analytics.petroleum import build_snapshot
from oilsignal.models import Citation, Claim, ClaimKind, Observation, Report, ReportSection
from oilsignal.reports.weekly import DEFAULT_METRICS, MetricSpec

_DEMAND_PROXY_SERIES = {
    "PET.GASPSUS.W",
    "PET.DISTPSUS.W",
    "PET.JETPSUS.W",
    "PET.TOTALPSUS.W",
}


class WeeklyPetroleumDelta:
    """Current-release week-over-week changes without repeating level claims."""

    def __init__(self, metrics: tuple[MetricSpec, ...] = DEFAULT_METRICS) -> None:
        self.metrics = metrics

    def build(self, observations: list[Observation]) -> Report:
        if not observations:
            raise ValueError("cannot build a delta without observations")

        maintained_series = {spec.series_id for spec in self.metrics}
        scoped_observations = [
            row for row in observations if row.series_id in maintained_series
        ]
        if not scoped_observations:
            raise ValueError("cannot build a delta without maintained-series observations")

        as_of = max(row.observation_date for row in scoped_observations)
        sections: list[ReportSection] = []
        for spec in self.metrics:
            rows = sorted(
                [row for row in scoped_observations if row.series_id == spec.series_id],
                key=lambda row: row.observation_date,
            )
            if len(rows) < 2:
                continue

            snapshot = build_snapshot(rows, spec.series_id, as_of=as_of)
            trace = snapshot.week_over_week
            if snapshot.as_of != as_of or trace is None:
                continue

            prior_date = min(trace.input_observation_dates)
            current_date = max(trace.input_observation_dates)
            prior = next(row for row in rows if row.observation_date == prior_date)
            current = next(row for row in rows if row.observation_date == current_date)
            label = spec.label
            if spec.series_id in _DEMAND_PROXY_SERIES:
                label = f"{label} (demand proxy)"

            change = trace.result
            if change > 0:
                change_text = f"increased by {change:,.1f} {trace.unit}"
            elif change < 0:
                change_text = f"decreased by {abs(change):,.1f} {trace.unit}"
            else:
                change_text = "were unchanged"

            claim = Claim(
                text=(
                    f"{label} {change_text} from {prior_date.isoformat()} "
                    f"to {current_date.isoformat()}."
                ),
                kind=ClaimKind.NUMERIC,
                citations=[
                    Citation(
                        source_url=prior.source_url,
                        series_id=prior.series_id,
                        observation_date=prior.observation_date,
                        calculation_id=trace.calculation_id,
                    ),
                    Citation(
                        source_url=current.source_url,
                        series_id=current.series_id,
                        observation_date=current.observation_date,
                        calculation_id=trace.calculation_id,
                    ),
                ],
                calculation=trace,
            )
            sections.append(ReportSection(heading=spec.section, claims=[claim]))

        if not sections:
            raise ValueError(
                f"no current-week week-over-week deltas are available for {as_of.isoformat()}"
            )

        report = Report(
            report_type="weekly_petroleum_delta",
            title=f"Weekly Petroleum Delta — {as_of.isoformat()}",
            as_of=as_of,
            sections=sections,
            metadata={
                "method": "deterministic",
                "event_type": "week_over_week_change",
                "changes_only": True,
                "series_count": len(sections),
                "scope": "Only maintained series updated on the current event week are included.",
                "disclaimer": "Decision support only; not trading or investment advice.",
            },
        )
        return validate_report(report)
