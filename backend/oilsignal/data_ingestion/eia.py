from __future__ import annotations

from typing import Any, TypeAlias

import httpx
from pydantic import BaseModel, Field

QueryScalar: TypeAlias = str | int | float | bool | None


class EIASeriesRequest(BaseModel):
    """Typed description of an EIA v2 data route."""

    route: str
    frequency: str = "weekly"
    data: list[str] = Field(default_factory=lambda: ["value"])
    facets: dict[str, list[str]] = Field(default_factory=dict)
    start: str | None = None
    end: str | None = None
    offset: int = Field(default=0, ge=0)
    length: int = Field(default=5000, ge=1, le=5000)


class EIAClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.eia.gov/v2",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.timeout = timeout

    async def fetch(self, request: EIASeriesRequest) -> dict[str, Any]:
        params: list[tuple[str, QueryScalar]] = [
            ("api_key", self.api_key),
            ("frequency", request.frequency),
            ("offset", request.offset),
            ("length", request.length),
        ]
        params.extend(("data[]", field) for field in request.data)
        for facet, values in request.facets.items():
            params.extend((f"facets[{facet}][]", value) for value in values)
        if request.start:
            params.append(("start", request.start))
        if request.end:
            params.append(("end", request.end))
        params.extend([("sort[0][column]", "period"), ("sort[0][direction]", "desc")])
        return await self._get_json(
            f"{self.base_url}/{request.route.strip('/')}/data/",
            params,
        )

    async def metadata(self, route: str) -> dict[str, Any]:
        return await self._get_json(
            f"{self.base_url}/{route.strip('/')}/",
            [("api_key", self.api_key)],
        )

    async def facet_values(self, route: str, facet: str) -> dict[str, Any]:
        return await self._get_json(
            f"{self.base_url}/{route.strip('/')}/facet/{facet}/",
            [("api_key", self.api_key)],
        )

    def public_data_url(self, request: EIASeriesRequest) -> str:
        """Return a stable citation URL that never includes the user's API key."""

        return f"{self.base_url}/{request.route.strip('/')}/data/"

    async def _get_json(
        self,
        url: str,
        params: list[tuple[str, QueryScalar]],
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self.timeout,
            transport=self.transport,
        ) as client:
            response = await client.get(url, params=httpx.QueryParams(params))
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("EIA response was not a JSON object")
        if "response" not in payload:
            raise ValueError("EIA response did not contain a response object")
        return payload
