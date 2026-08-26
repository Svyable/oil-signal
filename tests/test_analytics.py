from datetime import date
from pathlib import Path

from oilsignal.analytics.petroleum import build_snapshot
from oilsignal.data_ingestion.fixtures import FixtureIngestor, load_observations


FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


def test_snapshot_computes_transparent_comparisons(data_dir: Path) -> None:
    result = FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    observations = load_observations(result.parquet_path)

    snapshot = build_snapshot(observations, "PET.CRDUUS.W", as_of=date(2026, 8, 21))

    assert snapshot.current == 418_200
    assert snapshot.week_over_week is not None
    assert snapshot.week_over_week.result == 1_500
    assert snapshot.four_week_average is not None
    assert snapshot.four_week_average.result == 418_100
    assert snapshot.year_over_year is not None
    assert snapshot.year_over_year.result == -800
    assert snapshot.seasonal_low == 419_000
    assert snapshot.seasonal_high == 423_500


def test_padd2_distillate_snapshot_flags_decline(data_dir: Path) -> None:
    result = FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    observations = load_observations(result.parquet_path)
    snapshot = build_snapshot(observations, "PET.DISTP2.W")

    assert snapshot.week_over_week is not None
    assert snapshot.week_over_week.result == -700
    assert snapshot.year_over_year is not None
    assert snapshot.year_over_year.result == -2_200
