from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from oilsignal.agent.commerce import PaymentRejected, build_payment_requirement
from oilsignal.agent.pilot_gateway import (
    PILOT_CREDENTIAL_HEADER,
    PILOT_PROTOCOL,
    PilotAccessGateway,
)
from oilsignal.agent.runtime_gateway import build_runtime_payment_gateway
from oilsignal.api.app import create_app
from oilsignal.config import Settings
from oilsignal.data_ingestion.fixtures import FixtureIngestor
from oilsignal.storage.commerce import list_paid_fulfillments

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"
PILOT_KEY = "pilot_" + "a" * 40


def _requirement(sku: str = "fact-us-crude-stocks"):
    return build_payment_requirement(
        sku=sku,
        amount=Decimal("0.005"),
        currency="USD",
        evidence_sha256="b" * 64,
        description="Pilot evidence",
    )


def test_pilot_gateway_is_constant_contract_and_evidence_bound() -> None:
    gateway = PilotAccessGateway(
        PILOT_KEY,
        customer="acme-fuels",
        allowed_skus=frozenset({"fact-us-crude-stocks"}),
        reference="invoice-001",
    )
    requirement = _requirement()

    challenge = gateway.challenge(requirement)

    assert gateway.protocol == PILOT_PROTOCOL
    assert gateway.credential_headers == (PILOT_CREDENTIAL_HEADER,)
    assert challenge.protocol == PILOT_PROTOCOL
    assert challenge.response_headers["X-OilSignal-Pilot-Required"] == PILOT_CREDENTIAL_HEADER
    assert "OilSignalPilot" in challenge.response_headers["WWW-Authenticate"]

    with pytest.raises(PaymentRejected, match="key was rejected"):
        gateway.verify({}, requirement)
    with pytest.raises(PaymentRejected, match="key was rejected"):
        gateway.verify({PILOT_CREDENTIAL_HEADER: "wrong-credential"}, requirement)

    verified = gateway.verify({PILOT_CREDENTIAL_HEADER.lower(): PILOT_KEY}, requirement)

    assert verified.protocol == PILOT_PROTOCOL
    assert verified.external_id == requirement.external_id
    assert verified.reference == "invoice-001"
    assert verified.payer == "pilot:acme-fuels"
    assert verified.response_headers == {"X-OilSignal-Pilot-Access": "granted"}


def test_pilot_gateway_rejects_out_of_scope_products_and_unsafe_metadata() -> None:
    gateway = PilotAccessGateway(
        PILOT_KEY,
        customer="acme-fuels",
        allowed_skus=frozenset({"fact-us-crude-stocks"}),
    )

    with pytest.raises(PaymentRejected, match="not enabled"):
        gateway.verify(
            {PILOT_CREDENTIAL_HEADER: PILOT_KEY},
            _requirement("weekly-petroleum-delta"),
        )
    with pytest.raises(ValueError, match="at least 24"):
        PilotAccessGateway(
            "too-short",
            customer="acme-fuels",
            allowed_skus=frozenset({"fact-us-crude-stocks"}),
        )
    with pytest.raises(ValueError, match="customer label is invalid"):
        PilotAccessGateway(
            PILOT_KEY,
            customer="acme\r\nforged",
            allowed_skus=frozenset({"fact-us-crude-stocks"}),
        )


def test_runtime_gateway_builds_only_explicit_scoped_pilot() -> None:
    settings = Settings(
        _env_file=None,
        agent_pilot_access_key=PILOT_KEY,
        agent_pilot_customer="acme-fuels",
        agent_pilot_reference="deal-42",
        agent_pilot_skus="fact-us-crude-stocks,weekly-petroleum-delta",
    )

    gateway = build_runtime_payment_gateway(settings)

    assert isinstance(gateway, PilotAccessGateway)
    assert gateway.allowed_skus == frozenset(
        {"fact-us-crude-stocks", "weekly-petroleum-delta"}
    )
    assert gateway.reference == "deal-42"

    with pytest.raises(ValueError, match="must list at least one"):
        build_runtime_payment_gateway(
            Settings(_env_file=None, agent_pilot_access_key=PILOT_KEY)
        )
    with pytest.raises(ValueError, match="unknown founding pilot SKUs"):
        build_runtime_payment_gateway(
            Settings(
                _env_file=None,
                agent_pilot_access_key=PILOT_KEY,
                agent_pilot_skus="not-a-product",
            )
        )
    with pytest.raises(ValueError, match="mutually exclusive"):
        build_runtime_payment_gateway(
            Settings(
                _env_file=None,
                agent_pilot_access_key=PILOT_KEY,
                agent_pilot_skus="fact-us-crude-stocks",
                agent_payment_gateway_url="https://payments.example.test",
                agent_payment_gateway_protocol="x402-v2",
            )
        )


def test_pilot_access_turns_manual_commercial_agreement_into_audited_fulfillment(
    data_dir: Path,
) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    gateway = PilotAccessGateway(
        PILOT_KEY,
        customer="acme-fuels",
        allowed_skus=frozenset({"fact-us-crude-stocks"}),
        reference="invoice-001",
    )
    client = TestClient(
        create_app(
            data_dir,
            agent_sku_prices={
                "fact-us-crude-stocks": Decimal("0.005"),
                "weekly-petroleum-delta": Decimal("0.02"),
            },
            payment_gateway=gateway,
        )
    )
    fact_path = "/api/agent/products/fact-us-crude-stocks/evidence"

    quote = client.get("/api/agent/products/fact-us-crude-stocks/quote")
    challenge = client.get(fact_path)
    wrong = client.get(fact_path, headers={PILOT_CREDENTIAL_HEADER: "wrong-credential"})
    paid = client.get(fact_path, headers={PILOT_CREDENTIAL_HEADER: PILOT_KEY})
    out_of_scope = client.get(
        "/api/agent/products/weekly-petroleum-delta/evidence",
        headers={PILOT_CREDENTIAL_HEADER: PILOT_KEY},
    )

    assert quote.status_code == 200
    assert quote.json()["price"]["amount"] == "0.005"
    assert quote.json()["payment_protocols"] == [PILOT_PROTOCOL]
    assert challenge.status_code == 402
    assert challenge.headers["x-oilsignal-pilot-required"] == PILOT_CREDENTIAL_HEADER
    assert challenge.headers["vary"] == PILOT_CREDENTIAL_HEADER
    assert wrong.status_code == 402
    assert paid.status_code == 200
    assert paid.headers["x-oilsignal-pilot-access"] == "granted"
    assert paid.headers["x-oilsignal-payment-protocol"] == PILOT_PROTOCOL
    assert paid.headers["x-oilsignal-payment-reference"] == "invoice-001"
    assert paid.headers["x-oilsignal-payment-payer"] == "pilot:acme-fuels"
    assert paid.headers["x-oilsignal-fulfillment-audit-id"].startswith("ful_")
    assert PILOT_KEY not in str(paid.headers)
    assert PILOT_KEY not in paid.text
    assert out_of_scope.status_code == 402
    assert "not enabled" in out_of_scope.json()["detail"]

    audits = list_paid_fulfillments(data_dir / "metadata.sqlite")
    assert len(audits) == 1
    assert audits[0].sku == "fact-us-crude-stocks"
    assert audits[0].amount == Decimal("0.005")
    assert audits[0].currency == "USD"
    assert audits[0].protocol == PILOT_PROTOCOL
    assert audits[0].gateway_reference == "invoice-001"
    assert audits[0].payer == "pilot:acme-fuels"
    assert audits[0].evidence_sha256 == paid.json()["evidence_sha256"]
