from __future__ import annotations

from dataclasses import dataclass

from oilsignal.agent.validation import validate_report
from oilsignal.analytics.petroleum import SeriesSnapshot, build_snapshot
from oilsignal.models import Citation, Claim, ClaimKind, Observation, Report, ReportSection


@dataclass(frozen=True)
class MetricSpec:
    series_id: str
    label: str
    section: str


DEFAULT_METRICS = (
    MetricSpec("PET.CRDUUS.W", "U.S. crude oil stocks", "Crude inventories"),
    MetricSpec("PET.GASUS.W", "U.S. total gasoline stocks", "Gasoline inventories"),
    MetricSpec("PET.DISTUS.W", "U.S. distillate stocks", "Distillate inventories"),
    MetricSpec("PET.DISTP2.W", "PADD 2 distillate stocks", "Midwest distillate"),
    MetricSpec("PET.JETUS.W", "U.S. jet fuel stocks", "Jet fuel inventories"),
    MetricSpec("PET.UTILUS.W", "U.S. refinery utilization", "Refinery operations"),
    MetricSpec("PET.CRIMUS.W", "U.S. crude oil imports", "Crude imports"),
    MetricSpec(
        "PET.GASPSUS.W",
        "U.S. finished motor gasoline product supplied",
        "Gasoline demand proxy",
    ),
    MetricSpec(
        "PET.DISTPSUS.W",
        "U.S. distillate product supplied",
        "Distillate demand proxy",
    ),
    MetricSpec(
        "PET.JETPSUS.W",
        "U.S. jet fuel product supplied",
        "Jet fuel demand proxy",
    ),
    MetricSpec(
        "PET.TOTALPSUS.W",
        "U.S. petroleum products supplied",
        "Aggregate demand proxy",
    ),
)


class WeeklyPetroleumBrief:
    def __init__(self, metrics: tuple[MetricSpec, ...] = DEFAULT_METRICS) -> None:
        self.metrics = metrics

    def build(self, observations: list[Observation]) -> Report:
        if not observations:
            raise ValueError("cannot build a report without observations")
        as_of = max(row.observation_date for row in observations)
        sections: list[ReportSection] = []
        for spec in self.metrics:
            rows = sorted(
                [row for row in observations if row.series_id == spec.series_id],
                key=lambda row: row.observation_date,
            )
            if not rows:
                continue
            snapshot = build_snapshot(rows, spec.series_id, as_of=as_of)
            claim = self._snapshot_claim(spec, rows, snapshot)
            sections.append(ReportSection(heading=spec.section, claims=[claim]))

        report = Report(
            report_type="weekly_petroleum_brief",
            title=f"Weekly Petroleum Brief — {as_of.isoformat()}",
            as_of=as_of,
            sections=sections,
            metadata={
                "method": "deterministic",
                "series_count": len(sections),
                "disclaimer": "Decision support only; not trading or investment advice.",
            },
        )
        return validate_report(report)

    @staticmethod
    def _snapshot_claim(spec: MetricSpec, rows: list[Observation], snapshot: SeriesSnapshot) -> Claim:
        current = max(
            (row for row in rows if row.observation_date <= snapshot.as_of),
            key=lambda row: row.observation_date,
        )
        citations = [
            Citation(
                source_url=current.source_url,
                series_id=current.series_id,
                observation_date=current.observation_date,
            )
        ]

        if snapshot.week_over_week is None:
            text = f"{spec.label} were {snapshot.current:,.1f} {snapshot.unit}."
            return Claim(text=text, kind=ClaimKind.NUMERIC, citations=citations)

        change = snapshot.week_over_week.result
        direction = "increased" if change > 0 else "decreased" if change < 0 else "were unchanged"
        prior_date = min(snapshot.week_over_week.input_observation_dates)
        prior = next(row for row in rows if row.observation_date == prior_date)
        citations.append(
            Citation(
                source_url=prior.source_url,
                series_id=prior.series_id,
                observation_date=prior.observation_date,
            )
        )
        if change == 0:
            change_text = "were unchanged week over week"
        else:
            change_text = f"{direction} by {abs(change):,.1f} {snapshot.unit} week over week"
        text = f"{spec.label} were {snapshot.current:,.1f} {snapshot.unit} and {change_text}."
        return Claim(
            text=text,
            kind=ClaimKind.NUMERIC,
            citations=citations,
            calculation=snapshot.week_over_week,
        )
