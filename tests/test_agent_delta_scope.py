from datetime import UTC, date, datetime
from pathlib import Path

from oilsignal.agent.products import build_evidence_pack
from oilsignal.data_ingestion.fixtures import FixtureIngestor, load_observations
from oilsignal.freshness import check_wpsr_freshness
from oilsignal.models import Frequency, Observation

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


def test_unrelated_future_series_does_not_advance_delta_event_clock(data_dir: Path) -> None:
    result = FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    observations = load_observations(result.parquet_path)
    unrelated = Observation(
        series_id="LOCAL.UNRELATED.W",
        metric="local_metric",
        product="local_product",
        geography="US",
        frequency=Frequency.WEEKLY,
        unit="widgets",
        observation_date=date(2026, 8, 28),
        value=123.0,
        source_url="https://example.com/local-series",
        fetched_at=datetime(2026, 8, 29, 12, tzinfo=UTC),
        raw_hash="f" * 64,
    )
    with_extra = [*observations, unrelated]
    freshness = check_wpsr_freshness(with_extra, live_eia=False)

    pack = build_evidence_pack(
        "weekly-petroleum-delta",
        with_extra,
        freshness=freshness,
        data_source="fixture:eia",
        source_fetched_at=unrelated.fetched_at,
    )

    assert pack.as_of == "2026-08-21"
    assert all(row.series_id != "LOCAL.UNRELATED.W" for row in pack.observations)
    assert {row.observation_date for row in pack.observations} == {
        "2026-08-14",
        "2026-08-21",
    }
