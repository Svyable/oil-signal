from __future__ import annotations

from fastapi import FastAPI

from oilsignal.agent.commercial import CommercialCatalog, build_commercial_catalog


def attach_commercial_routes(app: FastAPI) -> None:
    @app.get("/.well-known/oilsignal-commercial.json", response_model=CommercialCatalog)
    def commercial_discovery() -> CommercialCatalog:
        return build_commercial_catalog()

    @app.get("/api/agent/offers", response_model=CommercialCatalog)
    def commercial_offers() -> CommercialCatalog:
        return build_commercial_catalog()
