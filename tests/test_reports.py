from datetime import date
from pathlib import Path

import pytest
from oilsignal.agent.validation import ClaimValidationError, validate_report
from oilsignal.data_ingestion.fixtures import FixtureIngestor, load_observations
from oilsignal.models import Claim, ClaimKind, Report, ReportSection
from oilsignal.reports.renderers import render_report
from oilsignal.reports.specialized import (
    DistillateSupplyRiskBrief,
    RefineryUtilizationWatch,
)
from oilsignal.reports.weekly import WeeklyPetroleumBrief

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


def _observations(data_dir: Path):  # type: ignore[no-untyped-def]
    result = FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    return load_observations(result.parquet_path)


def test_weekly_report_contains_structured_citations(data_dir: Path) -> None:
    report = WeeklyPetroleumBrief().build(_observations(data_dir))

    assert report.report_type == "weekly_petroleum_brief"
    assert report.as_of == date(2026, 8, 21)
    assert len(report.sections) == 3
    for claim in report.iter_claims():
        assert claim.citations
        assert claim.citations[0].series_id
        assert claim.citations[0].observation_date

    markdown = render_report(report, "markdown")
    html = render_report(report, "html")
    json_output = render_report(report, "json")
    assert "## Evidence" in markdown
    assert "<!doctype html>" in html
    assert "href=\"https://api.eia.gov" in html
    assert '"report_type": "weekly_petroleum_brief"' in json_output


def test_specialized_operational_briefs_are_available(data_dir: Path) -> None:
    observations = _observations(data_dir)
    distillate = DistillateSupplyRiskBrief().build(observations)
    refinery = RefineryUtilizationWatch().build(observations)

    assert distillate.report_type == "distillate_supply_risk_brief"
    assert distillate.iter_claims()[0].citations
    assert refinery.report_type == "refinery_utilization_watch"
    assert refinery.iter_claims()[0].citations


def test_claim_validator_rejects_uncited_numerical_statement() -> None:
    report = Report(
        report_type="test",
        title="Invalid report",
        as_of=date(2026, 8, 21),
        sections=[
            ReportSection(
                heading="Broken",
                claims=[
                    Claim(
                        text="Crude inventories rose by 1,500 thousand barrels.",
                        kind=ClaimKind.NUMERIC,
                    )
                ],
            )
        ],
    )
    with pytest.raises(ClaimValidationError, match="uncited numerical claim"):
        validate_report(report)
