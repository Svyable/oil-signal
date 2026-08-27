from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from oilsignal.data_ingestion.eia import EIASeriesRequest
from oilsignal.models import Frequency


class SeriesSpec(BaseModel):
    """Normalization contract for exactly one canonical OilSignal series."""

    canonical_series_id: str
    metric: str
    product: str
    geography: str = "US"
    unit: str
    request: EIASeriesRequest
    period_field: str = "period"
    value_field: str = "value"
    missing_values: list[str] = Field(default_factory=lambda: ["", "NA", "--", "-"])

    @model_validator(mode="after")
    def validate_request(self) -> SeriesSpec:
        try:
            Frequency(self.request.frequency)
        except ValueError as exc:
            raise ValueError(
                f"unsupported OilSignal observation frequency: {self.request.frequency}"
            ) from exc
        if self.value_field not in self.request.data:
            raise ValueError(
                f"value_field {self.value_field!r} must be included in request.data"
            )
        return self

    @property
    def frequency(self) -> Frequency:
        return Frequency(self.request.frequency)


class SeriesRegistry(BaseModel):
    version: int = 1
    note: str | None = None
    series: list[SeriesSpec]

    @model_validator(mode="after")
    def unique_series_ids(self) -> SeriesRegistry:
        ids = [spec.canonical_series_id for spec in self.series]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"duplicate canonical series IDs: {duplicates}")
        if not self.series:
            raise ValueError("series registry must contain at least one series")
        return self

    @classmethod
    def load(cls, path: Path) -> SeriesRegistry:
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))
