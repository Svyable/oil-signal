from pathlib import Path

from fastapi.testclient import TestClient
from oilsignal.agent.commercial import build_commercial_catalog
from oilsignal.agent.commercial_routes import attach_commercial_routes
from oilsignal.agent.products import product_exists
from oilsignal.api.app import create_app


def test_commercial_catalog_maps_value_offers_to_real_skus() -> None:
    catalog = build_commercial_catalog()

    assert catalog.category == "evidence-first petroleum decision support"
    assert {solution.id for solution in catalog.solutions} == {
        "downstream-supply-risk",
        "crude-flow-reconciliation",
        "agent-ready-petroleum-evidence",
    }
    assert catalog.pilot.evaluation_window == "2-4 weekly release cycles"
    for solution in catalog.solutions:
        assert solution.recommended_skus
        assert len(solution.quote_paths) == len(solution.recommended_skus)
        assert all(product_exists(sku) for sku in solution.recommended_skus)
        assert solution.pilot_success_metrics
        assert all(
            path == f"/api/agent/products/{sku}/quote"
            for path, sku in zip(solution.quote_paths, solution.recommended_skus, strict=True)
        )


def test_commercial_discovery_routes_match(data_dir: Path) -> None:
    app = create_app(data_dir=data_dir)
    attach_commercial_routes(app)
    client = TestClient(app)

    discovery = client.get("/.well-known/oilsignal-commercial.json")
    offers = client.get("/api/agent/offers")

    assert discovery.status_code == 200
    assert offers.status_code == 200
    assert discovery.json() == offers.json()
    assert discovery.json()["product_catalog_path"] == "/.well-known/oilsignal-agent.json"
    assert discovery.json()["change_manifest_path"] == "/api/agent/manifest"
