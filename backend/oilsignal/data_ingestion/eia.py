from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field


class EIASeriesRequest(BaseModel):
    """Typed description of an EIA v2 route.

    OilSignal deliberately keeps routes/configuration data-driven because EIA route and
    facet choices vary across petroleum datasets. No market values are hardcoded here.
    """

    route: str
    frequency: str = "weekly"
    data: list[str] = Field(default_factory=lambda: ["value"])
    facets: dict[str, list[str]] = Field(default_factory=dict)
    start: str | None = None
    end: str | None = None


class EIAClient:
    def __init__(self, api_key: str, base_url: str = "https://api.eia.gov/v2") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def fetch(self, request: EIASeriesRequest) -> dict[str, Any]:
        params: list[tuple[str, str | int | float | bool | None]] = [
            ("api_key", self.api_key),
            ("frequency", request.frequency),
        ]
        params.extend(("data[]", field) for field in request.data)
        for facet, values in request.facets.items():
            params.extend((f"facets[{facet}][]", value) for value in values)
        if request.start:
            params.append(("start", request.start))
        if request.end:
            params.append(("end", request.end))
        params.extend([("sort[0][column]", "period"), ("sort[0][direction]", "desc")])

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/{request.route.strip('/')}/data/",
                params=httpx.QueryParams(params),
            )
            response.raise_for_status()
            payload = response.json()
        if "response" not in payload:
            raise ValueError("EIA response did not contain a response object")
        return payload
