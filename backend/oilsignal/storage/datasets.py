from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel

from oilsignal.data_ingestion.fixtures import load_observations
from oilsignal.models import Observation


class DataStatus(BaseModel):
    available: bool
    parquet_path: str | None = None
    series_count: int = 0
    observation_count: int = 0
    latest_observation: date | None = None
    latest_fetched_at: datetime | None = None


def latest_parquet(data_dir: Path) -> Path:
    paths = list((data_dir / "parquet").glob("*.parquet"))
    if not paths:
        raise FileNotFoundError("no ingested Parquet data found")
    return max(paths, key=lambda path: path.stat().st_mtime_ns)


def load_latest_observations(data_dir: Path) -> list[Observation]:
    return load_observations(latest_parquet(data_dir))


def inspect_data(data_dir: Path) -> DataStatus:
    try:
        parquet_path = latest_parquet(data_dir)
    except FileNotFoundError:
        return DataStatus(available=False)
    observations = load_observations(parquet_path)
    if not observations:
        return DataStatus(available=False, parquet_path=str(parquet_path))
    return DataStatus(
        available=True,
        parquet_path=str(parquet_path),
        series_count=len({item.series_id for item in observations}),
        observation_count=len(observations),
        latest_observation=max(item.observation_date for item in observations),
        latest_fetched_at=max(item.fetched_at for item in observations),
    )
