from datetime import UTC, date, datetime

from oilsignal.freshness import (
    FreshnessState,
    WPSRReleaseCalendar,
    check_wpsr_freshness,
)
from oilsignal.models import Frequency, Observation


def _observation(
    series_id: str,
    observation_date: date,
    *,
    source_url: str = "https://api.eia.gov/v2/seriesid/PET.WCESTUS1.W/data/",
) -> Observation:
    return Observation(
        series_id=series_id,
        metric="inventory",
        product="petroleum",
        geography="US",
        frequency=Frequency.WEEKLY,
        unit="thousand barrels",
        observation_date=observation_date,
        value=100.0,
        source_url=source_url,
        fetched_at=datetime(2026, 8, 26, 15, tzinfo=UTC),
        raw_hash="a" * 64,
    )


def test_standard_release_waits_for_eia_api_grace_window() -> None:
    calendar = WPSRReleaseCalendar()

    before_api_grace = calendar.expected_week_ending(
        datetime(2026, 8, 26, 16, 29, tzinfo=UTC)
    )
    after_api_grace = calendar.expected_week_ending(
        datetime(2026, 8, 26, 16, 31, tzinfo=UTC)
    )

    assert before_api_grace == date(2026, 8, 14)
    assert after_api_grace == date(2026, 8, 21)


def test_holiday_override_delays_expected_week() -> None:
    calendar = WPSRReleaseCalendar()

    on_normal_wednesday = calendar.expected_week_ending(
        datetime(2026, 9, 9, 20, tzinfo=UTC)
    )
    after_delayed_release_grace = calendar.expected_week_ending(
        datetime(2026, 9, 10, 18, 1, tzinfo=UTC)
    )

    assert on_normal_wednesday == date(2026, 8, 28)
    assert after_delayed_release_grace == date(2026, 9, 4)


def test_live_dataset_fails_freshness_when_any_series_lags_expected_week() -> None:
    observations = [
        _observation("PET.CRDUUS.W", date(2026, 8, 21)),
        _observation("PET.DISTP2.W", date(2026, 8, 14)),
    ]

    result = check_wpsr_freshness(
        observations,
        now=datetime(2026, 8, 26, 16, 31, tzinfo=UTC),
    )

    assert result.status == FreshnessState.STALE
    assert result.expected_week_ending == date(2026, 8, 21)
    assert result.stale_series == ["PET.DISTP2.W"]


def test_synthetic_dataset_is_not_subject_to_live_release_gate() -> None:
    observations = [
        _observation(
            "PET.CRDUUS.W",
            date(2025, 1, 3),
            source_url="https://example.com/eia/fixture.csv",
        )
    ]

    result = check_wpsr_freshness(
        observations,
        now=datetime(2026, 8, 26, 16, 31, tzinfo=UTC),
    )

    assert result.status == FreshnessState.NOT_APPLICABLE
    assert result.expected_week_ending is None
