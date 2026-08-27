import asyncio
from datetime import UTC, date, datetime
from typing import Any

from oilsignal.data_ingestion.eia import EIASeriesRequest
from oilsignal.data_ingestion.registry import SeriesRegistry, SeriesSpec
from oilsignal.data_ingestion.verification import verify_eia_registry

NOW = datetime(2026, 8, 27, 3, 0, tzinfo=UTC)


class FakeRegistrySource:
    def __init__(self, payloads: dict[str, dict[str, Any] | Exception]) -> None:
        self.payloads = payloads
        self.requests: list[EIASeriesRequest] = []

    async def fetch(self, request: EIASeriesRequest) -> dict[str, Any]:
        self.requests.append(request)
        payload = self.payloads[request.route]
        if isinstance(payload, Exception):
            raise payload
        return payload


def _spec(series_id: str, route: str, *, wpsr: bool = True) -> SeriesSpec:
    return SeriesSpec(
        canonical_series_id=series_id,
        metric="inventory",
        product="petroleum",
        geography="US",
        unit="thousand barrels",
        release_family="wpsr" if wpsr else None,
        request=EIASeriesRequest(route=route, frequency="weekly"),
    )


def _payload(*periods: tuple[str, str], warning: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "apiVersion": "2.1.12",
        "response": {
            "frequency": "weekly",
            "data": [{"period": period, "value": value} for period, value in periods],
        },
    }
    if warning:
        payload["warning"] = warning
    return payload


def test_registry_verifier_accepts_current_wpsr_series_and_records_warning() -> None:
    source = FakeRegistrySource(
        {
            "seriesid/PET.WCESTUS1.W": _payload(
                ("2026-08-21", "420000"),
                ("2026-08-14", "421000"),
                warning="compatibility route",
            )
        }
    )
    registry = SeriesRegistry(
        verified_at=date(2026, 8, 26),
        series=[_spec("PET.CRDUUS.W", "seriesid/PET.WCESTUS1.W")],
    )

    result = asyncio.run(verify_eia_registry(registry, source, now=NOW))

    assert result.ok is True
    assert result.registry_verified_at == date(2026, 8, 26)
    series = result.series[0]
    assert series.ok is True
    assert series.source_series_id == "PET.WCESTUS1.W"
    assert series.latest_observation == date(2026, 8, 21)
    assert series.expected_observation == date(2026, 8, 21)
    assert series.api_version == "2.1.12"
    assert series.warnings == ["compatibility route"]
    assert source.requests[0].length == 2
    assert source.requests[0].start is None
    assert source.requests[0].end is None


def test_registry_verifier_fails_stale_wpsr_route() -> None:
    source = FakeRegistrySource(
        {
            "seriesid/PET.WDISTP21.W": _payload(
                ("2026-08-14", "26000"),
                ("2026-08-07", "26500"),
            )
        }
    )
    registry = SeriesRegistry(
        series=[_spec("PET.DISTP2.W", "seriesid/PET.WDISTP21.W")]
    )

    result = asyncio.run(verify_eia_registry(registry, source, now=NOW))

    assert result.ok is False
    assert result.series[0].latest_observation == date(2026, 8, 14)
    assert "trails expected WPSR week 2026-08-21" in result.series[0].errors[-1]


def test_registry_verifier_reports_route_errors_without_hiding_other_series() -> None:
    source = FakeRegistrySource(
        {
            "seriesid/GOOD": _payload(("2026-08-21", "10"), ("2026-08-14", "11")),
            "seriesid/BAD": RuntimeError("series unavailable"),
            "seriesid/MALFORMED": {
                "response": {
                    "frequency": "weekly",
                    "data": [{"period": "2026-08-21", "value": "not-a-number"}],
                }
            },
        }
    )
    registry = SeriesRegistry(
        series=[
            _spec("GOOD", "seriesid/GOOD"),
            _spec("BAD", "seriesid/BAD"),
            _spec("MALFORMED", "seriesid/MALFORMED"),
        ]
    )

    result = asyncio.run(verify_eia_registry(registry, source, now=NOW))

    assert result.ok is False
    assert [item.ok for item in result.series] == [True, False, False]
    assert "series unavailable" in result.series[1].errors[0]
    assert any("non-numeric" in error for error in result.series[2].errors)


def test_registry_verifier_can_skip_release_freshness_for_contract_only_checks() -> None:
    source = FakeRegistrySource(
        {"seriesid/OLD": _payload(("2020-01-03", "10"), ("2019-12-27", "11"))}
    )
    registry = SeriesRegistry(series=[_spec("OLD", "seriesid/OLD")])

    result = asyncio.run(
        verify_eia_registry(registry, source, now=NOW, enforce_freshness=False)
    )

    assert result.ok is True
    assert result.series[0].expected_observation is None
