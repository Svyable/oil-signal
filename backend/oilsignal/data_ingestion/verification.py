from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from oilsignal.data_ingestion.eia import EIASeriesRequest
from oilsignal.data_ingestion.registry import SeriesRegistry, SeriesSpec
from oilsignal.freshness import WPSRReleaseCalendar
from oilsignal.models import Frequency

EIA_API_DOCUMENTATION_URL = "https://www.eia.gov/opendata/documentation.php"


class EIARegistrySource(Protocol):
    async def fetch(self, request: EIASeriesRequest) -> dict[str, Any]: ...


class SeriesVerificationResult(BaseModel):
    canonical_series_id: str
    route: str
    source_series_id: str | None = None
    ok: bool
    checked_rows: int = 0
    latest_observation: date | None = None
    expected_observation: date | None = None
    api_version: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class RegistryVerificationResult(BaseModel):
    ok: bool
    checked_at: datetime
    registry_verified_at: date | None = None
    documentation_url: str = EIA_API_DOCUMENTATION_URL
    series: list[SeriesVerificationResult]


async def verify_eia_registry(
    registry: SeriesRegistry,
    client: EIARegistrySource,
    *,
    sample_length: int = 2,
    now: datetime | None = None,
    enforce_freshness: bool = True,
) -> RegistryVerificationResult:
    """Probe every registry route and return a complete source-contract audit."""

    if sample_length < 1 or sample_length > 5000:
        raise ValueError("sample_length must be between 1 and 5000")
    checked_at = now or datetime.now(UTC)
    if checked_at.tzinfo is None:
        raise ValueError("registry verification requires a timezone-aware datetime")
    checked_at = checked_at.astimezone(UTC)
    calendar = WPSRReleaseCalendar()
    results: list[SeriesVerificationResult] = []

    for spec in registry.series:
        result = await _verify_series(
            spec,
            client,
            sample_length=sample_length,
            checked_at=checked_at,
            calendar=calendar,
            enforce_freshness=enforce_freshness,
        )
        results.append(result)

    return RegistryVerificationResult(
        ok=all(result.ok for result in results),
        checked_at=checked_at,
        registry_verified_at=registry.verified_at,
        series=results,
    )


async def _verify_series(
    spec: SeriesSpec,
    client: EIARegistrySource,
    *,
    sample_length: int,
    checked_at: datetime,
    calendar: WPSRReleaseCalendar,
    enforce_freshness: bool,
) -> SeriesVerificationResult:
    warnings: list[str] = []
    errors: list[str] = []
    source_series_id = _source_series_id(spec.request.route)
    probe = spec.request.model_copy(
        update={"offset": 0, "length": sample_length, "start": None, "end": None}
    )

    try:
        payload = await client.fetch(probe)
    except Exception as exc:
        return SeriesVerificationResult(
            canonical_series_id=spec.canonical_series_id,
            route=spec.request.route,
            source_series_id=source_series_id,
            ok=False,
            errors=[f"{exc.__class__.__name__}: {str(exc)[:1000]}"],
        )

    api_version = payload.get("apiVersion")
    if api_version is not None and not isinstance(api_version, str):
        warnings.append(f"unexpected apiVersion type: {type(api_version).__name__}")
        api_version = str(api_version)
    warnings.extend(_extract_warnings(payload))

    response = payload.get("response")
    if not isinstance(response, dict):
        errors.append("response object is missing")
        rows: list[Any] = []
    else:
        returned_frequency = response.get("frequency")
        if isinstance(returned_frequency, str) and returned_frequency != spec.request.frequency:
            errors.append(
                f"frequency mismatch: registry={spec.request.frequency}, EIA={returned_frequency}"
            )
        raw_rows = response.get("data")
        if not isinstance(raw_rows, list):
            errors.append("response.data is not a list")
            rows = []
        else:
            rows = raw_rows

    if not rows:
        errors.append("probe returned no data rows")

    periods: list[date] = []
    seen_periods: set[date] = set()
    for index, raw_row in enumerate(rows):
        prefix = f"row {index}"
        if not isinstance(raw_row, dict):
            errors.append(f"{prefix}: row is not an object")
            continue
        raw_period = raw_row.get(spec.period_field)
        if raw_period is None:
            errors.append(f"{prefix}: missing {spec.period_field!r}")
        else:
            try:
                parsed_period = _parse_period(str(raw_period), spec.frequency)
            except ValueError as exc:
                errors.append(f"{prefix}: invalid period {raw_period!r}: {exc}")
            else:
                if parsed_period in seen_periods:
                    errors.append(f"{prefix}: duplicate period {parsed_period.isoformat()}")
                seen_periods.add(parsed_period)
                periods.append(parsed_period)

        raw_value = raw_row.get(spec.value_field)
        if raw_value is None or str(raw_value).strip() in spec.missing_values:
            errors.append(f"{prefix}: missing {spec.value_field!r}")
        else:
            try:
                float(raw_value)
            except (TypeError, ValueError):
                errors.append(f"{prefix}: non-numeric value {raw_value!r}")

    latest = max(periods) if periods else None
    expected: date | None = None
    if enforce_freshness and spec.release_family == "wpsr":
        expected = calendar.expected_week_ending(checked_at)
        if latest is None or latest < expected:
            errors.append(
                f"latest observation {latest or 'missing'} trails expected WPSR week "
                f"{expected.isoformat()}"
            )

    return SeriesVerificationResult(
        canonical_series_id=spec.canonical_series_id,
        route=spec.request.route,
        source_series_id=source_series_id,
        ok=not errors,
        checked_rows=len(rows),
        latest_observation=latest,
        expected_observation=expected,
        api_version=api_version,
        warnings=warnings,
        errors=errors,
    )


def _source_series_id(route: str) -> str | None:
    normalized = route.strip("/")
    prefix = "seriesid/"
    return normalized[len(prefix) :] if normalized.startswith(prefix) else None


def _extract_warnings(payload: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for key in ("warning", "warnings"):
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            warnings.append(value)
        else:
            warnings.append(json.dumps(value, sort_keys=True, default=str))
    return warnings


def _parse_period(value: str, frequency: Frequency) -> date:
    if frequency == Frequency.WEEKLY:
        return date.fromisoformat(value)
    if frequency == Frequency.MONTHLY:
        if len(value) == 7:
            return date.fromisoformat(f"{value}-01")
        return date.fromisoformat(value).replace(day=1)
    raise ValueError(f"unsupported verification frequency: {frequency}")
