import json
from decimal import Decimal
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from oilsignal.agent.http_payment_gateway import HttpPaymentGateway
from oilsignal.api.app import create_app
from oilsignal.data_ingestion.fixtures import FixtureIngestor

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


def test_remote_gateway_challenge_and_paid_retry(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        payload = json.loads(request.content)
        requirement = payload["requirement"]
        if request.url.path == "/oilsignal/challenge":
            return httpx.Response(
                200,
                json={
                    "protocol": "x402-v2",
                    "challenge_id": "challenge-1",
                    "response_headers": {"PAYMENT-REQUIRED": "challenge-token"},
                },
            )
        assert request.url.path == "/oilsignal/verify"
        assert payload["credentials"] == {"PAYMENT-SIGNATURE": "paid-signature"}
        return httpx.Response(
            200,
            json={
                "protocol": "x402-v2",
                "external_id": requirement["external_id"],
                "reference": "settlement-1",
                "payer": "agent-buyer",
                "response_headers": {"PAYMENT-RESPONSE": "receipt-token"},
            },
        )

    gateway = HttpPaymentGateway(
        "http://payments.local/oilsignal",
        protocol="x402-v2",
        credential_headers=("PAYMENT-SIGNATURE",),
        allow_insecure_http=True,
        transport=httpx.MockTransport(handler),
    )
    client = TestClient(
        create_app(
            data_dir,
            agent_unit_price_usd=Decimal("0.05"),
            payment_gateway=gateway,
        )
    )

    challenge = client.get("/api/agent/products/weekly-petroleum-evidence/evidence")
    assert challenge.status_code == 402
    assert challenge.headers["payment-required"] == "challenge-token"
    challenged = challenge.json()
    assert challenged["external_id"].endswith(challenged["evidence_sha256"])
    assert "claims" not in challenged

    paid = client.get(
        "/api/agent/products/weekly-petroleum-evidence/evidence",
        headers={"PAYMENT-SIGNATURE": "paid-signature"},
    )
    assert paid.status_code == 200
    pack = paid.json()
    assert paid.headers["payment-response"] == "receipt-token"
    assert paid.headers["x-oilsignal-payment-reference"] == "settlement-1"
    assert paid.headers["x-oilsignal-payment-payer"] == "agent-buyer"
    assert paid.headers["x-oilsignal-payment-external-id"].endswith(pack["evidence_sha256"])
    assert calls == ["/oilsignal/challenge", "/oilsignal/verify"]
