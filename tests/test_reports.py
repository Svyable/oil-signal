from datetime import date
from pathlib import Path

import pytest

from oilsignal.agent.validation import ClaimValidationError, validate_report
from oilsignal.data_ingestion.fixtures import FixtureIngestor, load_observations
from oilsignal.models import Claim, ClaimKind, Report, ReportSection
from oilsignal.reports.renderers import render_report
from oilsignal.reports.weekly import WeeklyPetroleumBrief


FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


def test_weekly_report_contains_structured_citations(data_dir: Path) -> None:
    result = FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    report = WeeklyPetroleumBrief().build(load_observations(result.parquet_path))

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
    assert '"report_type": "weekly_petroleum_brief"' in json_output


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
