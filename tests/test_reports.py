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


def test_distillate_brief_adds_demand_pressure_when_product_supplied_exists(
    data_dir: Path,
) -> None:
    observations = _observations(data_dir)
    source_rows = [row for row in observations if row.series_id == "PET.DISTP2.W"][-2:]
    demand_rows = [
        row.model_copy(
            update={
                "series_id": "PET.DISTPSUS.W",
                "metric": "product_supplied",
                "product": "distillate fuel oil",
                "geography": "US",
                "unit": "thousand barrels per day",
                "value": 4100.0 + index * 100.0,
            }
        )
        for index, row in enumerate(source_rows)
    ]

    report = DistillateSupplyRiskBrief().build([*observations, *demand_rows])

    assert len(report.iter_claims()) == 2
    assert report.sections[1].heading == "Demand pressure"
    demand_claim = report.sections[1].claims[0]
    assert "product supplied" in demand_claim.text
    assert all(citation.series_id == "PET.DISTPSUS.W" for citation in demand_claim.citations)


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
