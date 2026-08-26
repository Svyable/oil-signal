import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest

from oilsignal.data_ingestion.eia import EIAClient, EIASeriesRequest
from oilsignal.data_ingestion.fixtures import load_observations
from oilsignal.data_ingestion.live import EIAIngestor
from oilsignal.data_ingestion.registry import SeriesRegistry, SeriesSpec


class FakeEIAClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    async def fetch(self, request: EIASeriesRequest) -> dict[str, Any]:
        return self.payload

    def public_data_url(self, request: EIASeriesRequest) -> str:
        return f"https://api.eia.gov/v2/{request.route}/data/"


def _registry() -> SeriesRegistry:
    return SeriesRegistry(
        series=[
            SeriesSpec(
                canonical_series_id="TEST.CRude.W",
                metric="inventory",
                product="crude",
                geography="US",
                unit="thousand barrels",
                request=EIASeriesRequest(route="petroleum/test", frequency="weekly"),
            )
        ]
    )


def test_live_ingestion_writes_raw_parquet_and_reuses_identical_payload(data_dir: Path) -> None:
    payload = {
        "response": {
            "total": "2",
            "data": [
                {"period": "2026-08-07", "value": "101.5"},
                {"period": "2026-08-14", "value": "99.0"},
            ],
        }
    }
    ingestor = EIAIngestor(data_dir, FakeEIAClient(payload))

    first = asyncio.run(ingestor.ingest_registry(_registry()))
    second = asyncio.run(ingestor.ingest_registry(_registry()))

    assert first.rows_written == 2
    assert first.raw_dir.exists()
    assert first.parquet_path.exists()
    assert second.reused is True
    observations = load_observations(first.parquet_path)
    assert observations[-1].value == 99.0
    assert observations[-1].raw_hash


def test_live_ingestion_rejects_truncated_eia_response(data_dir: Path) -> None:
    payload = {
        "response": {
            "total": "3",
            "data": [
                {"period": "2026-08-07", "value": "101.5"},
                {"period": "2026-08-14", "value": "99.0"},
            ],
        }
    }

    with pytest.raises(ValueError, match="truncated"):
        asyncio.run(EIAIngestor(data_dir, FakeEIAClient(payload)).ingest_registry(_registry()))


def test_live_ingestion_rejects_duplicate_periods_from_underconstrained_facets(
    data_dir: Path,
) -> None:
    payload = {
        "response": {
            "total": "2",
            "data": [
                {"period": "2026-08-14", "value": "99.0", "area": "A"},
                {"period": "2026-08-14", "value": "98.0", "area": "B"},
            ],
        }
    }

    with pytest.raises(ValueError, match="under-constrained"):
        asyncio.run(EIAIngestor(data_dir, FakeEIAClient(payload)).ingest_registry(_registry()))


def test_eia_client_sends_key_but_public_citation_url_does_not() -> None:
    observed_url = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_url
        observed_url = str(request.url)
        return httpx.Response(
            200,
            json={"response": {"total": "1", "data": [{"period": "2026-08-14", "value": "1"}]}},
        )

    request = EIASeriesRequest(
        route="petroleum/test",
        facets={"area": ["US", "R20"]},
    )
    client = EIAClient("secret-key", transport=httpx.MockTransport(handler))

    asyncio.run(client.fetch(request))

    assert "secret-key" in observed_url
    assert "facets%5Barea%5D%5B%5D=US" in observed_url
    assert "secret-key" not in client.public_data_url(request)
