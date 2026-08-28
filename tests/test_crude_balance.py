from datetime import UTC, date, datetime

import pytest

from oilsignal.analytics.crude_balance import build_crude_balance
from oilsignal.models import Observation
from oilsignal.reports.specialized import CrudeBalanceWatch


def _row(
    series_id: str,
    metric: str,
    observation_date: date,
    value: float,
    unit: str = "thousand barrels per day",
) -> Observation:
    return Observation(
        series_id=series_id,
        metric=metric,
        product="crude oil",
        geography="US",
        frequency="weekly",
        unit=unit,
        observation_date=observation_date,
        value=value,
        source_url=f"https://api.eia.gov/v2/seriesid/{series_id}/data/",
        fetched_at=datetime(2026, 8, 27, 12, tzinfo=UTC),
        raw_hash=f"hash-{series_id}-{observation_date.isoformat()}",
    )


def _observations() -> list[Observation]:
    prior = date(2026, 8, 14)
    current = date(2026, 8, 21)
    rows = [
        _row("PET.CRPRODUS.W", "production", prior, 13550),
        _row("PET.CRIMUS.W", "imports", prior, 6100),
        _row("PET.CREXUS.W", "exports", prior, 4000),
        _row("PET.CRINUS.W", "refinery_input", prior, 17200),
        _row("PET.CRDUUS.W", "inventory", prior, 421000, "thousand barrels"),
        _row("PET.CRPRODUS.W", "production", current, 13600),
        _row("PET.CRIMUS.W", "imports", current, 6200),
        _row("PET.CREXUS.W", "exports", current, 3800),
        _row("PET.CRINUS.W", "refinery_input", current, 17300),
        _row("PET.CRDUUS.W", "inventory", current, 416100, "thousand barrels"),
    ]
    return rows


def test_crude_balance_reconciles_core_flows_to_stock_change() -> None:
    result = build_crude_balance(_observations())

    assert result.as_of == date(2026, 8, 21)
    assert result.core_flow_balance.result == pytest.approx(-1300.0)
    assert result.stock_change_rate.result == pytest.approx(-700.0)
    assert result.other_adjustment_residual.result == pytest.approx(600.0)
    assert result.stock_interval_days == 7


def test_crude_balance_fails_closed_without_aligned_flow_series() -> None:
    observations = [row for row in _observations() if row.series_id != "PET.CREXUS.W"]

    with pytest.raises(ValueError, match="aligned production, import, export, and refinery-input"):
        build_crude_balance(observations)


def test_crude_balance_watch_cites_every_derived_claim() -> None:
    report = CrudeBalanceWatch().build(_observations())

    assert report.report_type == "crude_balance_watch"
    assert report.as_of == date(2026, 8, 21)
    assert report.metadata["scope"].startswith("Partial deterministic flow reconciliation")
    balance_claims = report.sections[-2].claims + report.sections[-1].claims
    assert len(balance_claims) == 3
    for claim in balance_claims:
        assert claim.calculation is not None
        assert claim.citations
        assert all(
            citation.calculation_id == claim.calculation.calculation_id
            for citation in claim.citations
        )
