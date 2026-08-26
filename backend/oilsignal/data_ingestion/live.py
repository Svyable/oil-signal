from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

import polars as pl
from pydantic import BaseModel

from oilsignal.data_ingestion.eia import EIASeriesRequest
from oilsignal.data_ingestion.registry import SeriesRegistry, SeriesSpec
from oilsignal.models import Frequency, Observation
from oilsignal.storage.metadata import IngestionRunRow, get_ingestion_run, save_ingestion_run


class EIADataSource(Protocol):
    async def fetch(self, request: EIASeriesRequest) -> dict[str, Any]: ...

    def public_data_url(self, request: EIASeriesRequest) -> str: ...


class EIAIngestionResult(BaseModel):
    run_id: str
    series_count: int
    rows_written: int
    rows_skipped: int
    raw_dir: Path
    parquet_path: Path
    reused: bool = False


class EIAIngestor:
    """Normalize configured EIA v2 responses into auditable OilSignal observations."""

    def __init__(self, data_dir: Path, client: EIADataSource) -> None:
        self.data_dir = data_dir
        self.client = client

    async def ingest_registry(self, registry: SeriesRegistry) -> EIAIngestionResult:
        started = datetime.now(UTC)
        fetched: list[tuple[SeriesSpec, dict[str, Any], bytes, str]] = []
        fingerprint_parts = [registry.model_dump_json()]

        for spec in registry.series:
            payload = await self.client.fetch(spec.request)
            raw_bytes = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            digest = sha256(raw_bytes).hexdigest()
            fetched.append((spec, payload, raw_bytes, digest))
            fingerprint_parts.append(f"{spec.canonical_series_id}:{digest}")

        run_digest = sha256("\n".join(fingerprint_parts).encode("utf-8")).hexdigest()
        run_id = f"eia_{run_digest[:16]}"
        raw_dir = self.data_dir / "raw" / run_id
        parquet_path = self.data_dir / "parquet" / f"{run_id}.parquet"
        metadata_path = self.data_dir / "metadata.sqlite"

        existing = get_ingestion_run(metadata_path, run_id)
        if existing and raw_dir.exists() and parquet_path.exists():
            return EIAIngestionResult(
                run_id=run_id,
                series_count=len(registry.series),
                rows_written=existing.rows_written,
                rows_skipped=0,
                raw_dir=raw_dir,
                parquet_path=parquet_path,
                reused=True,
            )

        records: list[dict[str, object]] = []
        seen: set[tuple[str, date]] = set()
        rows_skipped = 0

        for spec, payload, _, digest in fetched:
            response = payload.get("response")
            if not isinstance(response, dict):
                raise ValueError(f"{spec.canonical_series_id}: response object is missing")
            rows = response.get("data")
            if not isinstance(rows, list):
                raise ValueError(f"{spec.canonical_series_id}: response.data is not a list")
            total = _parse_total(response.get("total"), len(rows))
            if total > len(rows):
                raise ValueError(
                    f"{spec.canonical_series_id}: EIA returned {len(rows)} of {total} rows; "
                    "constrain the registry date/facets instead of accepting truncated data"
                )

            for raw_row in rows:
                if not isinstance(raw_row, dict):
                    raise ValueError(f"{spec.canonical_series_id}: response row is not an object")
                raw_value = raw_row.get(spec.value_field)
                if raw_value is None or str(raw_value).strip() in spec.missing_values:
                    rows_skipped += 1
                    continue
                raw_period = raw_row.get(spec.period_field)
                if raw_period is None:
                    raise ValueError(
                        f"{spec.canonical_series_id}: row is missing {spec.period_field!r}"
                    )
                observation_date = _parse_period(str(raw_period), spec.frequency)
                key = (spec.canonical_series_id, observation_date)
                if key in seen:
                    raise ValueError(
                        f"{spec.canonical_series_id}: duplicate observation for "
                        f"{observation_date}; registry facets are likely under-constrained"
                    )
                seen.add(key)
                try:
                    value = float(raw_value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"{spec.canonical_series_id}: non-numeric value {raw_value!r}"
                    ) from exc
                observation = Observation(
                    series_id=spec.canonical_series_id,
                    metric=spec.metric,
                    product=spec.product,
                    geography=spec.geography,
                    frequency=spec.frequency,
                    unit=spec.unit,
                    observation_date=observation_date,
                    value=value,
                    source_url=self.client.public_data_url(spec.request),
                    fetched_at=started,
                    raw_hash=digest,
                )
                records.append(observation.model_dump(mode="json"))

        if not records:
            raise ValueError("EIA ingestion produced no usable observations")

        raw_dir.mkdir(parents=True, exist_ok=True)
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        for index, (spec, _, raw_bytes, _) in enumerate(fetched, start=1):
            filename = f"{index:02d}_{_safe_name(spec.canonical_series_id)}.json"
            (raw_dir / filename).write_bytes(raw_bytes)

        normalized = pl.DataFrame(records).sort(["series_id", "observation_date"])
        normalized.write_parquet(parquet_path)
        save_ingestion_run(
            metadata_path,
            IngestionRunRow(
                id=run_id,
                source="eia:v2",
                started_at=started,
                completed_at=datetime.now(UTC),
                status="completed",
                rows_written=normalized.height,
                raw_path=str(raw_dir),
                parquet_path=str(parquet_path),
            ),
        )
        return EIAIngestionResult(
            run_id=run_id,
            series_count=len(registry.series),
            rows_written=normalized.height,
            rows_skipped=rows_skipped,
            raw_dir=raw_dir,
            parquet_path=parquet_path,
        )


def _parse_total(value: object, fallback: int) -> int:
    if value is None:
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid EIA response total: {value!r}") from exc


def _parse_period(value: str, frequency: Frequency) -> date:
    if frequency == Frequency.WEEKLY:
        return date.fromisoformat(value)
    if frequency == Frequency.MONTHLY:
        if re.fullmatch(r"\d{4}-\d{2}", value):
            return date.fromisoformat(f"{value}-01")
        parsed = date.fromisoformat(value)
        return parsed.replace(day=1)
    raise ValueError(f"unsupported observation frequency: {frequency}")


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "series"
