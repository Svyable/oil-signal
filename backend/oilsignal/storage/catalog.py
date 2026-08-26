from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb


class ObservationCatalog:
    """Read normalized Parquet through DuckDB without copying it into another store."""

    def __init__(self, parquet_path: Path) -> None:
        if not parquet_path.exists():
            raise FileNotFoundError(parquet_path)
        self.parquet_path = parquet_path

    @property
    def _source(self) -> str:
        escaped = str(self.parquet_path).replace("'", "''")
        return f"read_parquet('{escaped}')"

    def latest(self, series_id: str) -> dict[str, Any] | None:
        query = f"""
            SELECT series_id, metric, product, geography, frequency, unit,
                   observation_date, value, source_url, fetched_at, raw_hash
            FROM {self._source}
            WHERE series_id = ?
            ORDER BY observation_date DESC
            LIMIT 1
        """
        with duckdb.connect() as connection:
            cursor = connection.execute(query, [series_id])
            row = cursor.fetchone()
            if row is None:
                return None
            columns = [item[0] for item in cursor.description]
        return dict(zip(columns, row, strict=True))

    def series_summary(self) -> list[dict[str, Any]]:
        query = f"""
            SELECT series_id, min(observation_date) AS first_observation,
                   max(observation_date) AS latest_observation, count(*) AS observations
            FROM {self._source}
            GROUP BY series_id
            ORDER BY series_id
        """
        with duckdb.connect() as connection:
            cursor = connection.execute(query)
            rows = cursor.fetchall()
            columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in rows]
