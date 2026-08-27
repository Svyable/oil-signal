from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from oilsignal.models import Frequency, Observation

EASTERN = ZoneInfo("America/New_York")
WPSR_SCHEDULE_URL = "https://www.eia.gov/petroleum/supply/weekly/schedule.php"
EIA_API_FAQ_URL = "https://www.eia.gov/opendata/faqs.php"


class FreshnessState(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    NOT_APPLICABLE = "not_applicable"


class DatasetFreshness(BaseModel):
    status: FreshnessState
    checked_at: datetime
    latest_observation: date | None = None
    expected_week_ending: date | None = None
    stale_series: list[str] = Field(default_factory=list)
    live_series_count: int = 0
    reason: str
    release_schedule_url: str = WPSR_SCHEDULE_URL
    api_latency_url: str = EIA_API_FAQ_URL


class StaleDatasetError(ValueError):
    """Raised when live WPSR-backed evidence is older than the expected release."""


def _eastern_datetime(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=EASTERN)


DEFAULT_2026_OVERRIDES: dict[date, datetime] = {
    date(2026, 1, 16): _eastern_datetime(2026, 1, 22, 12),
    date(2026, 2, 13): _eastern_datetime(2026, 2, 19, 12),
    date(2026, 5, 22): _eastern_datetime(2026, 5, 28, 12),
    date(2026, 9, 4): _eastern_datetime(2026, 9, 10, 12),
    date(2026, 10, 9): _eastern_datetime(2026, 10, 15, 12),
    date(2026, 11, 6): _eastern_datetime(2026, 11, 12, 12),
}


@dataclass(frozen=True)
class WPSRReleaseCalendar:
    """Release-aware freshness policy for EIA's Weekly Petroleum Status Report."""

    overrides: dict[date, datetime] = field(
        default_factory=lambda: dict(DEFAULT_2026_OVERRIDES)
    )
    api_grace: timedelta = timedelta(hours=2)

    def release_at(self, week_ending: date) -> datetime:
        if week_ending.weekday() != 4:
            raise ValueError("WPSR week_ending must be a Friday")
        override = self.overrides.get(week_ending)
        if override is not None:
            if override.tzinfo is None:
                raise ValueError("WPSR release overrides must be timezone-aware")
            return override
        release_day = week_ending + timedelta(days=5)
        return datetime.combine(release_day, time(10, 30), tzinfo=EASTERN)

    def expected_week_ending(self, now: datetime) -> date:
        if now.tzinfo is None:
            raise ValueError("freshness checks require a timezone-aware datetime")
        local_now = now.astimezone(EASTERN)
        days_since_friday = (local_now.weekday() - 4) % 7
        candidate = local_now.date() - timedelta(days=days_since_friday)
        for _ in range(104):
            if now >= self.release_at(candidate).astimezone(UTC) + self.api_grace:
                return candidate
            candidate -= timedelta(days=7)
        raise RuntimeError("could not resolve an expected WPSR week ending")


def check_wpsr_freshness(
    observations: list[Observation],
    *,
    now: datetime | None = None,
    calendar: WPSRReleaseCalendar | None = None,
) -> DatasetFreshness:
    checked_at = now or datetime.now(UTC)
    if checked_at.tzinfo is None:
        raise ValueError("freshness checks require a timezone-aware datetime")

    live_rows = [
        row
        for row in observations
        if row.frequency == Frequency.WEEKLY
        and urlparse(str(row.source_url)).hostname == "api.eia.gov"
    ]
    if not live_rows:
        return DatasetFreshness(
            status=FreshnessState.NOT_APPLICABLE,
            checked_at=checked_at,
            reason="dataset contains no weekly observations cited to api.eia.gov",
        )

    release_calendar = calendar or WPSRReleaseCalendar()
    expected = release_calendar.expected_week_ending(checked_at)
    latest_by_series: dict[str, date] = {}
    for row in live_rows:
        previous = latest_by_series.get(row.series_id)
        if previous is None or row.observation_date > previous:
            latest_by_series[row.series_id] = row.observation_date

    stale_series = sorted(
        series_id
        for series_id, latest in latest_by_series.items()
        if latest < expected
    )
    latest_observation = max(latest_by_series.values())
    if stale_series:
        return DatasetFreshness(
            status=FreshnessState.STALE,
            checked_at=checked_at,
            latest_observation=latest_observation,
            expected_week_ending=expected,
            stale_series=stale_series,
            live_series_count=len(latest_by_series),
            reason=(
                f"{len(stale_series)} live series trail the expected WPSR week ending "
                f"{expected.isoformat()}"
            ),
        )

    return DatasetFreshness(
        status=FreshnessState.FRESH,
        checked_at=checked_at,
        latest_observation=latest_observation,
        expected_week_ending=expected,
        live_series_count=len(latest_by_series),
        reason=f"all live weekly EIA series cover {expected.isoformat()} or later",
    )


def require_fresh_wpsr(
    observations: list[Observation],
    *,
    now: datetime | None = None,
    calendar: WPSRReleaseCalendar | None = None,
) -> DatasetFreshness:
    freshness = check_wpsr_freshness(observations, now=now, calendar=calendar)
    if freshness.status == FreshnessState.STALE:
        series = ", ".join(freshness.stale_series[:5])
        if len(freshness.stale_series) > 5:
            series += ", ..."
        raise StaleDatasetError(
            f"live EIA evidence is stale for expected week ending "
            f"{freshness.expected_week_ending}: {series}"
        )
    return freshness
