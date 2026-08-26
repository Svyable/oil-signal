from pathlib import Path

import polars as pl

from oilsignal.data_ingestion.fixtures import FixtureIngestor, load_observations
from oilsignal.storage.metadata import get_ingestion_run


FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


def test_fixture_ingestion_creates_parquet_and_provenance(data_dir: Path) -> None:
    result = FixtureIngestor(data_dir).ingest_csv(FIXTURE)

    assert result.rows_written == 23
    assert result.parquet_path.exists()
    frame = pl.read_parquet(result.parquet_path)
    assert {"source_url", "series_id", "observation_date", "fetched_at", "raw_hash"} <= set(frame.columns)

    run = get_ingestion_run(data_dir / "metadata.sqlite", result.run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.rows_written == 23
    assert len(load_observations(result.parquet_path)) == 23


def test_fixture_ingestion_is_idempotent(data_dir: Path) -> None:
    ingestor = FixtureIngestor(data_dir)
    first = ingestor.ingest_csv(FIXTURE)
    second = ingestor.ingest_csv(FIXTURE)

    assert first.run_id == second.run_id
    assert second.reused is True
