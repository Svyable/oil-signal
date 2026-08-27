from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import polars as pl
from pydantic import BaseModel

from oilsignal.models import Observation
from oilsignal.storage.metadata import IngestionRunRow, get_ingestion_run, save_ingestion_run

REQUIRED_COLUMNS = {
    "series_id",
    "metric",
    "product",
    "geography",
    "frequency",
    "unit",
    "observation_date",
    "value",
}


class IngestionResult(BaseModel):
    run_id: str
    rows_written: int
    raw_path: Path
    parquet_path: Path
    reused: bool = False


class FixtureIngestor:
    """Offline ingestion path used by tests, demos, and deterministic development."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def ingest_csv(
        self,
        fixture_path: Path,
        *,
        source_url: str = "https://api.eia.gov/v2/petroleum/fixture",
        fetched_at: datetime | None = None,
    ) -> IngestionResult:
        payload = fixture_path.read_bytes()
        digest = sha256(payload).hexdigest()
        run_id = f"fixture_{digest[:16]}"
        raw_path = self.data_dir / "raw" / f"{run_id}.csv"
        parquet_path = self.data_dir / "parquet" / f"{run_id}.parquet"
        metadata_path = self.data_dir / "metadata.sqlite"

        existing = get_ingestion_run(metadata_path, run_id)
        if existing and parquet_path.exists() and raw_path.exists():
            return IngestionResult(
                run_id=run_id,
                rows_written=existing.rows_written,
                raw_path=raw_path,
                parquet_path=parquet_path,
                reused=True,
            )

        started = fetched_at or datetime.now(UTC)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(payload)

        frame = pl.read_csv(fixture_path, try_parse_dates=True)
        missing = REQUIRED_COLUMNS - set(frame.columns)
        if missing:
            raise ValueError(f"fixture missing required columns: {sorted(missing)}")

        records: list[dict[str, object]] = []
        for row in frame.iter_rows(named=True):
            observation = Observation.model_validate(
                {
                    **row,
                    "source_url": source_url,
                    "fetched_at": started,
                    "raw_hash": digest,
                }
            )
            records.append(observation.model_dump(mode="json"))

        normalized = pl.DataFrame(records)
        normalized.write_parquet(parquet_path)
        save_ingestion_run(
            metadata_path,
            IngestionRunRow(
                id=run_id,
                source="fixture:eia",
                started_at=started,
                completed_at=datetime.now(UTC),
                status="completed",
                rows_written=normalized.height,
                raw_path=str(raw_path),
                parquet_path=str(parquet_path),
            ),
        )
        return IngestionResult(
            run_id=run_id,
            rows_written=normalized.height,
            raw_path=raw_path,
            parquet_path=parquet_path,
        )


def load_observations(parquet_path: Path) -> list[Observation]:
    return [Observation.model_validate(row) for row in pl.read_parquet(parquet_path).to_dicts()]
