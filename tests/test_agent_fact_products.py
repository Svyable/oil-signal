from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from oilsignal.agent.commerce import (
    PaymentChallenge,
    PaymentRejected,
    PaymentRequirement,
    VerifiedPayment,
)
from oilsignal.agent.products import build_evidence_pack
from oilsignal.api.app import create_app
from oilsignal.data_ingestion.fixtures import FixtureIngestor
from oilsignal.freshness import check_wpsr_freshness
from oilsignal.models import Frequency, Observation
from oilsignal.reports.facts import FACT_PRODUCT_SPECS
from oilsignal.storage.commerce import list_paid_fulfillments

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


class FactPaymentGateway:
    protocol = "x402-v2"
    credential_headers = ("PAYMENT-SIGNATURE",)

    def __init__(self) -> None:
        self.challenge_calls = 0
        self.verify_calls = 0

    def challenge(self, requirement: PaymentRequirement) -> PaymentChallenge:
        self.challenge_calls += 1
        return PaymentChallenge(
            protocol=self.protocol,
            challenge_id="fact-challenge",
            response_headers={"PAYMENT-REQUIRED": "fact-payment-required"},
        )

    def verify(
        self,
        request_headers: Mapping[str, str],
        requirement: PaymentRequirement,
    ) -> VerifiedPayment:
        self.verify_calls += 1
        signature = request_headers.get("payment-signature") or request_headers.get(
            "PAYMENT-SIGNATURE"
        )
        if signature != "fact-paid":
            raise PaymentRejected("PAYMENT-SIGNATURE header is required")
        return VerifiedPayment(
            protocol=self.protocol,
            response_headers={"PAYMENT-RESPONSE": "fact-settled"},
            external_id=requirement.external_id,
            reference="fact-settlement-123",
            payer="agent:micro-buyer",
        )


def test_catalog_exposes_only_curated_fact_skus(data_dir: Path) -> None:
    client = TestClient(create_app(data_dir, agent_unit_price_usd=Decimal("0.01")))

    response = client.get("/api/agent/products")

    assert response.status_code == 200
    facts = [product for product in response.json()["products"] if product["product_kind"] == "fact"]
    expected = {spec.sku: spec.series_id for spec in FACT_PRODUCT_SPECS}
    assert {product["sku"]: product["series_id"] for product in facts} == expected
    assert all("maintained_series_only" in product["evidence_guarantees"] for product in facts)
    assert all(product["price"]["amount"] == "0.01" for product in facts)


def test_fact_evidence_is_small_cited_and_deterministic(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    client = TestClient(create_app(data_dir))

    response = client.get("/api/agent/products/fact-us-crude-stocks/evidence")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sku"] == "fact-us-crude-stocks"
    assert payload["report_type"] == "series_fact"
    assert payload["as_of"] == "2026-08-21"
    assert len(payload["claims"]) == 2
    assert {row["series_id"] for row in payload["observations"]} == {"PET.CRDUUS.W"}
    assert [(row["observation_date"], row["value"]) for row in payload["observations"]] == [
        ("2026-08-14", 416700.0),
        ("2026-08-21", 418200.0),
    ]
    assert all(row["raw_hash"] for row in payload["observations"])
    change_claim = next(claim for claim in payload["claims"] if claim["calculation"])
    assert change_claim["calculation"]["operation"] == "week_over_week"
    assert change_claim["calculation"]["result"] == 1500.0
    assert change_claim["calculation"]["input_series_ids"] == ["PET.CRDUUS.W"]
    assert response.headers["x-oilsignal-evidence-sha256"] == payload["evidence_sha256"]


def test_fact_state_binds_to_exact_fact_evidence_digest(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    client = TestClient(create_app(data_dir))

    state = client.get("/api/agent/products/fact-us-refinery-utilization/state")
    evidence = client.get("/api/agent/products/fact-us-refinery-utilization/evidence")

    assert state.status_code == 200
    assert evidence.status_code == 200
    state_payload = state.json()
    evidence_payload = evidence.json()
    assert state_payload["evidence_sha256"] == evidence_payload["evidence_sha256"]
    assert state_payload["as_of"] == evidence_payload["as_of"] == "2026-08-21"
    assert state_payload["fulfillment_path"].endswith(
        "/fact-us-refinery-utilization/evidence"
    )


def test_paid_fact_reuses_402_and_fulfillment_audit(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    gateway = FactPaymentGateway()
    client = TestClient(
        create_app(
            data_dir,
            agent_unit_price_usd=Decimal("0.01"),
            payment_gateway=gateway,
        )
    )
    path = "/api/agent/products/fact-padd2-distillate-stocks/evidence"

    challenge = client.get(path)
    paid = client.get(path, headers={"PAYMENT-SIGNATURE": "fact-paid"})

    assert challenge.status_code == 402
    assert challenge.json()["sku"] == "fact-padd2-distillate-stocks"
    assert challenge.json()["amount"] == "0.01"
    assert challenge.json()["resource_path"] == path
    assert "claims" not in challenge.json()
    assert paid.status_code == 200
    assert paid.headers["payment-response"] == "fact-settled"
    assert paid.headers["x-oilsignal-payment-reference"] == "fact-settlement-123"
    assert gateway.challenge_calls == 1
    assert gateway.verify_calls == 2

    audits = list_paid_fulfillments(data_dir / "metadata.sqlite")
    assert len(audits) == 1
    assert audits[0].sku == "fact-padd2-distillate-stocks"
    assert audits[0].resource_path == path
    assert audits[0].gateway_reference == "fact-settlement-123"
    assert audits[0].evidence_sha256 == paid.json()["evidence_sha256"]


def test_unavailable_fact_fails_before_payment(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    gateway = FactPaymentGateway()
    client = TestClient(
        create_app(
            data_dir,
            agent_unit_price_usd=Decimal("0.01"),
            payment_gateway=gateway,
        )
    )

    response = client.get("/api/agent/products/fact-us-crude-production/evidence")

    assert response.status_code == 409
    assert "PET.CRPRODUS.W" in response.json()["detail"]
    assert gateway.challenge_calls == 0
    assert gateway.verify_calls == 0
    assert list_paid_fulfillments(data_dir / "metadata.sqlite") == []


def test_product_supplied_fact_preserves_demand_proxy_semantics() -> None:
    observations = [
        Observation(
            series_id="PET.GASPSUS.W",
            metric="product_supplied",
            product="finished motor gasoline",
            geography="US",
            frequency=Frequency.WEEKLY,
            unit="thousand barrels per day",
            observation_date=date(2026, 8, 14),
            value=9100.0,
            source_url="https://www.eia.gov/example/gasoline",
            fetched_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
            raw_hash="a" * 64,
        ),
        Observation(
            series_id="PET.GASPSUS.W",
            metric="product_supplied",
            product="finished motor gasoline",
            geography="US",
            frequency=Frequency.WEEKLY,
            unit="thousand barrels per day",
            observation_date=date(2026, 8, 21),
            value=9250.0,
            source_url="https://www.eia.gov/example/gasoline",
            fetched_at=datetime(2026, 8, 27, 12, tzinfo=UTC),
            raw_hash="b" * 64,
        ),
    ]
    freshness = check_wpsr_freshness(observations, live_eia=False)

    pack = build_evidence_pack(
        "fact-us-gasoline-product-supplied",
        observations,
        freshness=freshness,
        data_source="fixture:eia",
        source_fetched_at=observations[-1].fetched_at,
    )

    assert pack.report_type == "series_fact"
    assert len(pack.claims) == 2
    assert all("demand proxy" in claim.text for claim in pack.claims)
    assert {row.series_id for row in pack.observations} == {"PET.GASPSUS.W"}
