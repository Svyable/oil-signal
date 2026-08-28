from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from oilsignal.agent.products import build_evidence_pack
from oilsignal.api.app import create_app
from oilsignal.data_ingestion.fixtures import FixtureIngestor, load_observations
from oilsignal.freshness import check_wpsr_freshness

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


def test_agent_catalog_is_machine_discoverable_and_priceable(data_dir: Path) -> None:
    client = TestClient(create_app(data_dir, agent_unit_price_usd=Decimal("0.05")))

    discovery = client.get("/.well-known/oilsignal-agent.json")
    catalog = client.get("/api/agent/products")

    assert discovery.status_code == 200
    assert catalog.status_code == 200
    payload = discovery.json()
    assert payload == catalog.json()
    assert payload["openapi_path"] == "/openapi.json"
    assert {product["sku"] for product in payload["products"]} == {
        "weekly-petroleum-evidence",
        "distillate-risk-evidence",
        "refinery-utilization-evidence",
        "crude-balance-evidence",
    }
    assert all(product["price"]["amount"] == "0.05" for product in payload["products"])
    assert all(product["price"]["enforcement"] == "external" for product in payload["products"])


def test_agent_quote_does_not_claim_payment_support_when_unconfigured(data_dir: Path) -> None:
    client = TestClient(create_app(data_dir))

    response = client.get("/api/agent/products/weekly-petroleum-evidence/quote")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available_for_purchase"] is False
    assert payload["price"] is None
    assert payload["payment_enforcement"] == "not_configured"
    assert payload["payment_protocols"] == []


def test_evidence_pack_has_stable_digest_raw_hashes_and_etag(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    client = TestClient(create_app(data_dir, agent_unit_price_usd=Decimal("0.05")))

    first = client.get("/api/agent/products/weekly-petroleum-evidence/evidence")
    second = client.get("/api/agent/products/weekly-petroleum-evidence/evidence")

    assert first.status_code == 200
    assert second.status_code == 200
    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["evidence_sha256"] == second_payload["evidence_sha256"]
    assert first.headers["etag"] == f'W/"sha256:{first_payload["evidence_sha256"]}"'
    assert first.headers["x-oilsignal-sku"] == "weekly-petroleum-evidence"
    assert first_payload["freshness"]["status"] == "not_applicable"
    assert first_payload["claims"]
    assert first_payload["observations"]
    assert all(row["raw_hash"] for row in first_payload["observations"])

    calculated = [claim for claim in first_payload["claims"] if claim["calculation"]]
    assert calculated
    for claim in calculated:
        calculation_fingerprint = claim["calculation"]["fingerprint"]
        assert calculation_fingerprint
        assert all(
            citation["calculation_fingerprint"] == calculation_fingerprint
            for citation in claim["citations"]
        )


def test_evidence_endpoint_returns_304_for_semantically_matching_etag(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    client = TestClient(create_app(data_dir))
    first = client.get("/api/agent/products/refinery-utilization-evidence/evidence")
    weak_etag = first.headers["etag"]

    cached = client.get(
        "/api/agent/products/refinery-utilization-evidence/evidence",
        headers={"If-None-Match": weak_etag},
    )
    strong_form = client.get(
        "/api/agent/products/refinery-utilization-evidence/evidence",
        headers={"If-None-Match": weak_etag.removeprefix("W/")},
    )

    assert first.status_code == 200
    assert weak_etag.startswith('W/"sha256:')
    assert cached.status_code == 304
    assert cached.content == b""
    assert cached.headers["etag"] == weak_etag
    assert cached.headers["x-oilsignal-evidence-sha256"] == first.json()["evidence_sha256"]
    assert strong_form.status_code == 304


def test_evidence_digest_changes_when_cited_source_hash_changes(data_dir: Path) -> None:
    result = FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    observations = load_observations(result.parquet_path)
    freshness = check_wpsr_freshness(observations, live_eia=False)
    fetched_at = max(row.fetched_at for row in observations)
    first = build_evidence_pack(
        "refinery-utilization-evidence",
        observations,
        freshness=freshness,
        data_source="fixture:eia",
        source_fetched_at=fetched_at,
        generated_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
    )

    cited = {(row.series_id, row.observation_date) for row in first.observations}
    changed = [
        row.model_copy(update={"raw_hash": "f" * 64})
        if (row.series_id, row.observation_date.isoformat())
        in {(series_id, date) for series_id, date in cited}
        else row
        for row in observations
    ]
    second = build_evidence_pack(
        "refinery-utilization-evidence",
        changed,
        freshness=freshness,
        data_source="fixture:eia",
        source_fetched_at=fetched_at + timedelta(seconds=30),
        generated_at=datetime(2026, 8, 28, 13, 0, tzinfo=UTC),
    )

    assert first.evidence_sha256 != second.evidence_sha256


def test_unknown_agent_product_is_404(data_dir: Path) -> None:
    client = TestClient(create_app(data_dir))

    quote = client.get("/api/agent/products/not-a-product/quote")
    evidence = client.get("/api/agent/products/not-a-product/evidence")

    assert quote.status_code == 404
    assert evidence.status_code == 404
