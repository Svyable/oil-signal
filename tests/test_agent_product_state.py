from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from oilsignal.agent.commerce import PaymentRequirement
from oilsignal.agent.products import build_evidence_pack, quote_agent_product
from oilsignal.agent.state import build_agent_product_state
from oilsignal.api.app import create_app
from oilsignal.data_ingestion.fixtures import FixtureIngestor, load_observations
from oilsignal.freshness import DatasetFreshness, FreshnessState, check_wpsr_freshness
from oilsignal.storage.commerce import list_paid_fulfillments

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


class PassivePaymentGateway:
    protocol = "x402-v2"
    credential_headers = ("PAYMENT-SIGNATURE",)

    def __init__(self) -> None:
        self.challenge_calls = 0
        self.verify_calls = 0

    def challenge(self, requirement: PaymentRequirement):
        self.challenge_calls += 1
        raise AssertionError("product-state polling must not challenge for payment")

    def verify(self, request_headers: Mapping[str, str], requirement: PaymentRequirement):
        self.verify_calls += 1
        raise AssertionError("product-state polling must not verify payment")


def test_product_state_is_discoverable_compact_and_payment_side_effect_free(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    gateway = PassivePaymentGateway()
    paid_client = TestClient(
        create_app(
            data_dir,
            agent_unit_price_usd=Decimal("0.05"),
            payment_gateway=gateway,
        )
    )

    catalog = paid_client.get("/api/agent/products").json()
    weekly = next(
        product for product in catalog["products"] if product["sku"] == "weekly-petroleum-evidence"
    )
    assert weekly["state_path"] == "/api/agent/products/weekly-petroleum-evidence/state"

    state_response = paid_client.get(weekly["state_path"])

    assert state_response.status_code == 200
    state = state_response.json()
    assert state["sku"] == "weekly-petroleum-evidence"
    assert state["fulfillment_available"] is True
    assert state["available_for_purchase"] is True
    assert state["price"]["amount"] == "0.05"
    assert state["price"]["enforcement"] == "http_402"
    assert state["payment_enforcement"] == "http_402"
    assert state["payment_protocols"] == ["x402-v2"]
    assert state["freshness"]["status"] == "not_applicable"
    assert state["fulfillment_path"] == weekly["evidence_path"]
    assert state_response.headers["x-oilsignal-state-sha256"] == state["state_sha256"]
    assert state_response.headers["x-oilsignal-evidence-sha256"] == state["evidence_sha256"]
    assert "claims" not in state
    assert "observations" not in state
    assert gateway.challenge_calls == 0
    assert gateway.verify_calls == 0
    assert list_paid_fulfillments(data_dir / "metadata.sqlite") == []

    free_client = TestClient(create_app(data_dir))
    evidence = free_client.get(weekly["evidence_path"])
    assert evidence.status_code == 200
    assert evidence.json()["evidence_sha256"] == state["evidence_sha256"]
    assert evidence.json()["as_of"] == state["as_of"]


def test_product_state_etag_is_stable_and_supports_free_revalidation(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    client = TestClient(create_app(data_dir, agent_unit_price_usd=Decimal("0.05")))
    path = "/api/agent/products/refinery-utilization-evidence/state"

    first = client.get(path)
    second = client.get(path)
    cached = client.get(path, headers={"If-None-Match": first.headers["etag"]})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers["etag"] == second.headers["etag"]
    assert first.json()["state_sha256"] == second.json()["state_sha256"]
    assert first.json()["freshness"]["checked_at"] != second.json()["freshness"]["checked_at"]
    assert cached.status_code == 304
    assert cached.content == b""
    assert cached.headers["etag"] == first.headers["etag"]


def test_product_state_fingerprint_changes_with_commercial_terms(data_dir: Path) -> None:
    result = FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    observations = load_observations(result.parquet_path)
    freshness = check_wpsr_freshness(observations, live_eia=False)
    pack = build_evidence_pack(
        "distillate-risk-evidence",
        observations,
        freshness=freshness,
        data_source="fixture:eia",
        source_fetched_at=max(row.fetched_at for row in observations),
    )

    cheap = build_agent_product_state(
        pack,
        quote_agent_product("distillate-risk-evidence", unit_price_usd=Decimal("0.05")),
    )
    expensive = build_agent_product_state(
        pack,
        quote_agent_product("distillate-risk-evidence", unit_price_usd=Decimal("0.06")),
    )

    assert cheap.evidence_sha256 == expensive.evidence_sha256
    assert cheap.state_sha256 != expensive.state_sha256


def test_stale_product_state_is_visible_but_not_fulfillable(data_dir: Path) -> None:
    result = FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    observations = load_observations(result.parquet_path)
    stale = DatasetFreshness(
        status=FreshnessState.STALE,
        checked_at=max(row.fetched_at for row in observations),
        latest_observation=max(row.observation_date for row in observations),
        expected_week_ending=max(row.observation_date for row in observations),
        stale_series=["PET.CRDUUS.W"],
        live_series_count=1,
        reason="synthetic stale product-state test",
    )
    pack = build_evidence_pack(
        "weekly-petroleum-evidence",
        observations,
        freshness=stale,
        data_source="eia:v2",
        source_fetched_at=max(row.fetched_at for row in observations),
    )
    state = build_agent_product_state(
        pack,
        quote_agent_product("weekly-petroleum-evidence", unit_price_usd=Decimal("0.05")),
    )

    assert state.freshness.status == FreshnessState.STALE
    assert state.fulfillment_available is False


def test_unknown_product_state_is_404(data_dir: Path) -> None:
    client = TestClient(create_app(data_dir))

    response = client.get("/api/agent/products/not-a-product/state")

    assert response.status_code == 404
