from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, model_validator


class Frequency(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ClaimKind(StrEnum):
    FACT = "fact"
    NUMERIC = "numeric"
    INTERPRETATION = "interpretation"


class Observation(BaseModel):
    series_id: str
    metric: str
    product: str
    geography: str = "US"
    frequency: Frequency
    unit: str
    observation_date: date
    value: float
    source_url: HttpUrl
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_hash: str


class Citation(BaseModel):
    source: str = "EIA"
    source_url: HttpUrl
    series_id: str
    observation_date: date
    calculation_id: str | None = None


class CalculationTrace(BaseModel):
    calculation_id: str = Field(default_factory=lambda: f"calc_{uuid4().hex[:12]}")
    operation: str
    expression: str
    input_series_ids: list[str]
    input_observation_dates: list[date]
    inputs: dict[str, float]
    result: float
    unit: str


class Claim(BaseModel):
    claim_id: str = Field(default_factory=lambda: f"claim_{uuid4().hex[:12]}")
    text: str
    kind: ClaimKind
    citations: list[Citation] = Field(default_factory=list)
    calculation: CalculationTrace | None = None

    @model_validator(mode="after")
    def calculation_is_cited(self) -> Claim:
        if self.calculation and self.citations:
            for citation in self.citations:
                if citation.calculation_id is None:
                    citation.calculation_id = self.calculation.calculation_id
        return self


class ReportSection(BaseModel):
    heading: str
    claims: list[Claim]


class Report(BaseModel):
    report_id: str = Field(default_factory=lambda: f"report_{uuid4().hex[:12]}")
    report_type: str
    title: str
    as_of: date
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sections: list[ReportSection]
    metadata: dict[str, Any] = Field(default_factory=dict)

    def iter_claims(self) -> list[Claim]:
        return [claim for section in self.sections for claim in section.claims]
