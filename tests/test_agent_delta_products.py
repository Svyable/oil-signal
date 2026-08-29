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
from oilsignal.data_ingestion.fixtures import FixtureIngestor, load_observations
from oilsignal.freshness import check_wpsr_freshness
from oilsignal.models import Frequency, Observation
from oilsignal.storage.commerce import list_paid_fulfillments

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


class DeltaPaymentGateway:
    protocol = "x402-v2"
    credential_headers = ("PAYMENT-SIGNATURE",)

    def __init__(self) -> None:
        self.challenge_calls = 0
        self.verify_calls = 0

    def challenge(self, requirement: PaymentRequirement) -> PaymentChallenge:
        self.challenge_calls += 1
        return PaymentChallenge(
            protocol=self.protocol,
            challenge_id="delta-challenge",
            response_headers={"PAYMENT-REQUIRED": "delta-payment-required"},
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
        if signature != "delta-paid":
            raise PaymentRejected("PAYMENT-SIGNATURE header is required")
        return VerifiedPayment(
            protocol=self.protocol,
            response_headers={"PAYMENT-RESPONSE": "delta-settled"},
            external_id=requirement.external_id,
            reference="delta-settlement-123",
            payer="agent:event-buyer",
        )


def test_catalog_exposes_weekly_delta_product(data_dir: Path) -> None:
    client = TestClient(create_app(data_dir, agent_unit_price_usd=Decimal("0.02")))

    response = client.get("/api/agent/products")

    assert response.status_code == 200
    delta = next(
        product
        for product in response.json()["products"]
        if product["sku"] == "weekly-petroleum-delta"
    )
    assert delta["product_kind"] == "delta"
    assert delta["series_id"] is None
    assert delta["price"]["amount"] == "0.02"
    assert "current_event_week_only" in delta["evidence_guarantees"]
    assert "week_over_week_changes_only" in delta["evidence_guarantees"]
    assert delta["state_path"] == "/api/agent/products/weekly-petroleum-delta/state"
    assert delta["evidence_path"] == "/api/agent/products/weekly-petroleum-delta/evidence"


def test_delta_evidence_contains_only_current_week_change_claims(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    client = TestClient(create_app(data_dir))

    response = client.get("/api/agent/products/weekly-petroleum-delta/evidence")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sku"] == "weekly-petroleum-delta"
    assert payload["report_type"] == "weekly_petroleum_delta"
    assert payload["as_of"] == "2026-08-21"
    assert len(payload["claims"]) == 3
    assert len(payload["observations"]) == 6
    assert {row["series_id"] for row in payload["observations"]} == {
        "PET.CRDUUS.W",
        "PET.DISTP2.W",
        "PET.UTILUS.W",
    }
    assert all(claim["calculation"] is not None for claim in payload["claims"])
    assert all(
        claim["calculation"]["operation"] == "week_over_week"
        for claim in payload["claims"]
    )
    assert all(len(claim["citations"]) == 2 for claim in payload["claims"])
    assert all(
        "from 2026-08-14 to 2026-08-21" in claim["text"]
        for claim in payload["claims"]
    )
    assert not any("were 418,200.0" in claim["text"] for claim in payload["claims"])
    assert all(row["raw_hash"] for row in payload["observations"])
    assert response.headers["x-oilsignal-evidence-sha256"] == payload["evidence_sha256"]


def test_delta_omits_lagging_series_from_current_event(data_dir: Path) -> None:
    result = FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    observations = load_observations(result.parquet_path)
    current_event = [
        row
        for row in observations
        if not (
            row.series_id == "PET.UTILUS.W"
            and row.observation_date == date(2026, 8, 21)
        )
    ]
    freshness = check_wpsr_freshness(current_event, live_eia=False)

    pack = build_evidence_pack(
        "weekly-petroleum-delta",
        current_event,
        freshness=freshness,
        data_source="fixture:eia",
        source_fetched_at=max(row.fetched_at for row in current_event),
    )

    assert pack.as_of == "2026-08-21"
    assert {row.series_id for row in pack.observations} == {
        "PET.CRDUUS.W",
        "PET.DISTP2.W",
    }
    assert all("refinery utilization" not in claim.text.lower() for claim in pack.claims)


def test_delta_preserves_product_supplied_demand_proxy_semantics() -> None:
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
        "weekly-petroleum-delta",
        observations,
        freshness=freshness,
        data_source="fixture:eia",
        source_fetched_at=observations[-1].fetched_at,
    )

    assert len(pack.claims) == 1
    assert "demand proxy" in pack.claims[0].text
    assert pack.claims[0].calculation is not None
    assert pack.claims[0].calculation.result == 150.0


def test_delta_state_supports_free_semantic_revalidation(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    client = TestClient(create_app(data_dir))
    state_path = "/api/agent/products/weekly-petroleum-delta/state"

    first = client.get(state_path)
    cached = client.get(state_path, headers={"If-None-Match": first.headers["etag"]})
    evidence = client.get("/api/agent/products/weekly-petroleum-delta/evidence")

    assert first.status_code == 200
    assert cached.status_code == 304
    assert cached.content == b""
    assert evidence.status_code == 200
    assert first.json()["evidence_sha256"] == evidence.json()["evidence_sha256"]
    assert first.json()["as_of"] == evidence.json()["as_of"] == "2026-08-21"


def test_paid_delta_reuses_402_and_fulfillment_audit(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    gateway = DeltaPaymentGateway()
    client = TestClient(
        create_app(
            data_dir,
            agent_unit_price_usd=Decimal("0.02"),
            payment_gateway=gateway,
        )
    )
    path = "/api/agent/products/weekly-petroleum-delta/evidence"

    challenge = client.get(path)
    paid = client.get(path, headers={"PAYMENT-SIGNATURE": "delta-paid"})

    assert challenge.status_code == 402
    assert challenge.json()["sku"] == "weekly-petroleum-delta"
    assert challenge.json()["amount"] == "0.02"
    assert challenge.json()["resource_path"] == path
    assert "claims" not in challenge.json()
    assert paid.status_code == 200
    assert paid.headers["payment-response"] == "delta-settled"
    assert paid.headers["x-oilsignal-payment-reference"] == "delta-settlement-123"
    assert gateway.challenge_calls == 1
    assert gateway.verify_calls == 2

    audits = list_paid_fulfillments(data_dir / "metadata.sqlite")
    assert len(audits) == 1
    assert audits[0].sku == "weekly-petroleum-delta"
    assert audits[0].resource_path == path
    assert audits[0].gateway_reference == "delta-settlement-123"
    assert audits[0].evidence_sha256 == paid.json()["evidence_sha256"]
