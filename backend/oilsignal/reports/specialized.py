from __future__ import annotations

from oilsignal.agent.validation import validate_report
from oilsignal.models import Observation, Report
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
