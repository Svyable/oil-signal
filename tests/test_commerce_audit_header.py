from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from oilsignal.agent.commerce import (
    PaymentChallenge,
    PaymentRejected,
    PaymentRequirement,
    VerifiedPayment,
)
from oilsignal.api.app import create_app
from oilsignal.data_ingestion.fixtures import FixtureIngestor
from oilsignal.storage.commerce import list_paid_fulfillments

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


class AuditHeaderCollisionGateway:
    protocol = "test-pay"
    credential_headers = ("Authorization",)

    def challenge(self, requirement: PaymentRequirement) -> PaymentChallenge:
        return PaymentChallenge(
            protocol=self.protocol,
            response_headers={"WWW-Authenticate": "Payment test"},
        )

    def verify(
        self,
        request_headers: Mapping[str, str],
        requirement: PaymentRequirement,
    ) -> VerifiedPayment:
        if request_headers.get("authorization") != "Payment paid":
            raise PaymentRejected()
        return VerifiedPayment(
            protocol=self.protocol,
            response_headers={"X-OilSignal-Fulfillment-Audit-ID": "forged"},
            external_id=requirement.external_id,
            reference="settlement-123",
        )


def test_gateway_cannot_override_fulfillment_audit_id(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    client = TestClient(
        create_app(
            data_dir,
            agent_unit_price_usd=Decimal("0.05"),
            payment_gateway=AuditHeaderCollisionGateway(),
        )
    )

    response = client.get(
        "/api/agent/products/weekly-petroleum-evidence/evidence",
        headers={"Authorization": "Payment paid"},
    )

    assert response.status_code == 502
    assert "reserved headers" in response.json()["detail"]
    assert list_paid_fulfillments(data_dir / "metadata.sqlite") == []
