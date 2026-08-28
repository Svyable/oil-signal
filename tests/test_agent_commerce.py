from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from oilsignal.agent.commerce import (
    PaymentChallenge,
    PaymentGatewayUnavailable,
    PaymentRejected,
    PaymentRequirement,
    VerifiedPayment,
)
from oilsignal.api.app import create_app
from oilsignal.data_ingestion.fixtures import FixtureIngestor

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


class FakePaymentGateway:
    protocol = "mpp"

    def __init__(self) -> None:
        self.challenges: list[PaymentRequirement] = []
        self.verifications: list[PaymentRequirement] = []
        self.unavailable = False
        self.mismatched_receipt = False

    def challenge(self, requirement: PaymentRequirement) -> PaymentChallenge:
        if self.unavailable:
            raise PaymentGatewayUnavailable("payment service unavailable")
        self.challenges.append(requirement)
        return PaymentChallenge(
            protocol=self.protocol,
            challenge_id=f"challenge-{len(self.challenges)}",
            www_authenticate=(
                'Payment id="challenge-1", method="test", intent="charge"'
            ),
        )

    def verify(
        self,
        authorization: str,
        requirement: PaymentRequirement,
    ) -> VerifiedPayment:
        if self.unavailable:
            raise PaymentGatewayUnavailable("payment service unavailable")
        self.verifications.append(requirement)
        if authorization != "Payment paid-credential":
            raise PaymentRejected("payment credential was rejected")
        external_id = "wrong-external-id" if self.mismatched_receipt else requirement.external_id
        return VerifiedPayment(
            protocol=self.protocol,
            receipt_header="receipt-token",
            external_id=external_id,
            reference="settlement-123",
            payer="agent:buyer",
        )


def _paid_client(data_dir: Path, gateway: FakePaymentGateway) -> TestClient:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    return TestClient(
        create_app(
            data_dir,
            agent_unit_price_usd=Decimal("0.05"),
            payment_gateway=gateway,
        )
    )


def test_paid_evidence_returns_402_without_leaking_pack(data_dir: Path) -> None:
    gateway = FakePaymentGateway()
    client = _paid_client(data_dir, gateway)

    response = client.get("/api/agent/products/weekly-petroleum-evidence/evidence")

    assert response.status_code == 402
    assert response.headers["www-authenticate"].startswith("Payment ")
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["status"] == 402
    assert payload["sku"] == "weekly-petroleum-evidence"
    assert payload["amount"] == "0.05"
    assert payload["currency"] == "USD"
    assert payload["payment_protocol"] == "mpp"
    assert payload["challenge_id"] == "challenge-1"
    assert payload["external_id"].endswith(payload["evidence_sha256"])
    assert "claims" not in payload
    assert "observations" not in payload
    assert gateway.challenges[0].evidence_sha256 == payload["evidence_sha256"]

    quote = client.get("/api/agent/products/weekly-petroleum-evidence/quote").json()
    assert quote["payment_enforcement"] == "http_402"
    assert quote["payment_protocols"] == ["mpp"]
    assert quote["price"]["enforcement"] == "http_402"


def test_paid_evidence_returns_gateway_receipt_bound_to_pack(data_dir: Path) -> None:
    gateway = FakePaymentGateway()
    client = _paid_client(data_dir, gateway)

    response = client.get(
        "/api/agent/products/refinery-utilization-evidence/evidence",
        headers={"Authorization": "Payment paid-credential"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert response.headers["payment-receipt"] == "receipt-token"
    assert response.headers["x-oilsignal-payment-protocol"] == "mpp"
    assert response.headers["x-oilsignal-payment-reference"] == "settlement-123"
    assert response.headers["x-oilsignal-payment-payer"] == "agent:buyer"
    assert response.headers["x-oilsignal-payment-external-id"].endswith(
        payload["evidence_sha256"]
    )
    requirement = gateway.verifications[0]
    assert requirement.evidence_sha256 == payload["evidence_sha256"]
    assert requirement.external_id == response.headers["x-oilsignal-payment-external-id"]


def test_invalid_payment_gets_fresh_402_challenge(data_dir: Path) -> None:
    gateway = FakePaymentGateway()
    client = _paid_client(data_dir, gateway)

    response = client.get(
        "/api/agent/products/weekly-petroleum-evidence/evidence",
        headers={"Authorization": "Payment bad-credential"},
    )

    assert response.status_code == 402
    assert response.json()["detail"] == "payment credential was rejected"
    assert len(gateway.verifications) == 1
    assert len(gateway.challenges) == 1


def test_unchanged_revalidation_is_free_before_payment(data_dir: Path) -> None:
    gateway = FakePaymentGateway()
    client = _paid_client(data_dir, gateway)
    first = client.get(
        "/api/agent/products/distillate-risk-evidence/evidence",
        headers={"Authorization": "Payment paid-credential"},
    )
    assert first.status_code == 200
    verification_count = len(gateway.verifications)

    cached = client.get(
        "/api/agent/products/distillate-risk-evidence/evidence",
        headers={"If-None-Match": first.headers["etag"]},
    )

    assert cached.status_code == 304
    assert cached.content == b""
    assert len(gateway.verifications) == verification_count
    assert gateway.challenges == []


def test_gateway_without_price_does_not_gate_open_core(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    gateway = FakePaymentGateway()
    client = TestClient(create_app(data_dir, payment_gateway=gateway))

    response = client.get("/api/agent/products/weekly-petroleum-evidence/evidence")

    assert response.status_code == 200
    assert gateway.challenges == []
    assert gateway.verifications == []


def test_gateway_unavailable_fails_closed(data_dir: Path) -> None:
    gateway = FakePaymentGateway()
    gateway.unavailable = True
    client = _paid_client(data_dir, gateway)

    response = client.get("/api/agent/products/weekly-petroleum-evidence/evidence")

    assert response.status_code == 503
    assert response.json()["detail"] == "payment service unavailable"


def test_mismatched_receipt_binding_is_rejected(data_dir: Path) -> None:
    gateway = FakePaymentGateway()
    gateway.mismatched_receipt = True
    client = _paid_client(data_dir, gateway)

    response = client.get(
        "/api/agent/products/weekly-petroleum-evidence/evidence",
        headers={"Authorization": "Payment paid-credential"},
    )

    assert response.status_code == 502
    assert "different evidence requirement" in response.json()["detail"]
