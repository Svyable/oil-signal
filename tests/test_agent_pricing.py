from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oilsignal.agent.commerce import (
    PaymentChallenge,
    PaymentRejected,
    PaymentRequirement,
    VerifiedPayment,
    build_payment_requirement,
)
from oilsignal.agent.pricing import ProductPricingPolicy
from oilsignal.api.app import create_app
from oilsignal.config import Settings
from oilsignal.data_ingestion.fixtures import FixtureIngestor
from oilsignal.storage.commerce import list_paid_fulfillments

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


class PricingGateway:
    protocol = "x402-v2"
    credential_headers = ("PAYMENT-SIGNATURE",)

    def __init__(self) -> None:
        self.challenges: list[PaymentRequirement] = []
        self.verifications: list[PaymentRequirement] = []

    def challenge(self, requirement: PaymentRequirement) -> PaymentChallenge:
        self.challenges.append(requirement)
        return PaymentChallenge(
            protocol=self.protocol,
            challenge_id=f"challenge-{len(self.challenges)}",
            response_headers={"PAYMENT-REQUIRED": "pricing-required"},
        )

    def verify(
        self,
        request_headers: Mapping[str, str],
        requirement: PaymentRequirement,
    ) -> VerifiedPayment:
        self.verifications.append(requirement)
        signature = request_headers.get("payment-signature") or request_headers.get(
            "PAYMENT-SIGNATURE"
        )
        if signature != "pricing-paid":
            raise PaymentRejected("PAYMENT-SIGNATURE header is required")
        return VerifiedPayment(
            protocol=self.protocol,
            response_headers={"PAYMENT-RESPONSE": "pricing-settled"},
            external_id=requirement.external_id,
            reference=f"settlement-{requirement.sku}",
        )


def test_pricing_policy_resolves_override_fallback_and_unpriced() -> None:
    policy = ProductPricingPolicy(
        default_amount=Decimal("0.05"),
        currency="usd",
        sku_amounts={
            "fact-us-crude-stocks": Decimal("0.005"),
            "refinery-utilization-evidence": None,
        },
    )

    assert policy.currency == "USD"
    assert policy.amount_for("fact-us-crude-stocks") == Decimal("0.005")
    assert policy.amount_for("weekly-petroleum-evidence") == Decimal("0.05")
    assert policy.amount_for("refinery-utilization-evidence") is None

    with pytest.raises(ValueError, match="cannot be negative"):
        ProductPricingPolicy(sku_amounts={"fact-us-crude-stocks": Decimal("-0.01")})


def test_settings_parse_json_sku_price_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "OILSIGNAL_AGENT_SKU_PRICES",
        '{"fact-us-crude-stocks":"0.007","refinery-utilization-evidence":null}',
    )

    configured = Settings(_env_file=None)

    assert configured.agent_sku_prices["fact-us-crude-stocks"] == Decimal("0.007")
    assert configured.agent_sku_prices["refinery-utilization-evidence"] is None


def test_unknown_sku_price_override_fails_app_construction(data_dir: Path) -> None:
    with pytest.raises(ValueError, match="unknown agent SKU price overrides: typo-sku"):
        create_app(
            data_dir,
            agent_sku_prices={"typo-sku": Decimal("0.01")},
        )


def test_catalog_quote_and_state_share_same_sku_price_policy(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    overrides = {
        "fact-us-crude-stocks": Decimal("0.005"),
        "refinery-utilization-evidence": None,
    }
    client = TestClient(
        create_app(
            data_dir,
            agent_unit_price_usd=Decimal("0.05"),
            agent_sku_prices=overrides,
        )
    )

    catalog = client.get("/api/agent/products").json()["products"]
    by_sku = {product["sku"]: product for product in catalog}
    fact_quote = client.get("/api/agent/products/fact-us-crude-stocks/quote").json()
    brief_quote = client.get("/api/agent/products/weekly-petroleum-evidence/quote").json()
    open_quote = client.get("/api/agent/products/refinery-utilization-evidence/quote").json()
    fact_state = client.get("/api/agent/products/fact-us-crude-stocks/state").json()

    assert by_sku["fact-us-crude-stocks"]["price"]["amount"] == "0.005"
    assert by_sku["weekly-petroleum-evidence"]["price"]["amount"] == "0.05"
    assert by_sku["refinery-utilization-evidence"]["price"] is None
    assert fact_quote["price"]["amount"] == "0.005"
    assert brief_quote["price"]["amount"] == "0.05"
    assert open_quote["available_for_purchase"] is False
    assert open_quote["price"] is None
    assert fact_state["price"]["amount"] == "0.005"


def test_price_override_changes_state_not_evidence(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    path = "/api/agent/products/fact-us-crude-stocks/state"
    cheap = TestClient(
        create_app(
            data_dir,
            agent_sku_prices={"fact-us-crude-stocks": Decimal("0.005")},
        )
    ).get(path)
    expensive = TestClient(
        create_app(
            data_dir,
            agent_sku_prices={"fact-us-crude-stocks": Decimal("0.009")},
        )
    ).get(path)

    assert cheap.status_code == expensive.status_code == 200
    assert cheap.json()["evidence_sha256"] == expensive.json()["evidence_sha256"]
    assert cheap.json()["state_sha256"] != expensive.json()["state_sha256"]
    assert cheap.json()["price"]["amount"] == "0.005"
    assert expensive.json()["price"]["amount"] == "0.009"


def test_paid_fact_uses_override_while_brief_uses_fallback(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    gateway = PricingGateway()
    client = TestClient(
        create_app(
            data_dir,
            agent_unit_price_usd=Decimal("0.05"),
            agent_sku_prices={"fact-us-crude-stocks": Decimal("0.005")},
            payment_gateway=gateway,
        )
    )
    fact_path = "/api/agent/products/fact-us-crude-stocks/evidence"
    brief_path = "/api/agent/products/weekly-petroleum-evidence/evidence"

    fact_challenge = client.get(fact_path)
    brief_challenge = client.get(brief_path)
    paid_fact = client.get(fact_path, headers={"PAYMENT-SIGNATURE": "pricing-paid"})

    assert fact_challenge.status_code == 402
    assert fact_challenge.json()["amount"] == "0.005"
    assert ":USD:0.005:sha256:" in fact_challenge.json()["external_id"]
    assert brief_challenge.status_code == 402
    assert brief_challenge.json()["amount"] == "0.05"
    assert ":USD:0.05:sha256:" in brief_challenge.json()["external_id"]
    assert paid_fact.status_code == 200

    audits = list_paid_fulfillments(data_dir / "metadata.sqlite")
    assert len(audits) == 1
    assert audits[0].sku == "fact-us-crude-stocks"
    assert audits[0].amount == Decimal("0.005")
    assert audits[0].currency == "USD"
    assert audits[0].external_id == paid_fact.headers["x-oilsignal-payment-external-id"]


def test_null_override_keeps_sku_open_even_with_gateway(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    gateway = PricingGateway()
    client = TestClient(
        create_app(
            data_dir,
            agent_unit_price_usd=Decimal("0.05"),
            agent_sku_prices={"refinery-utilization-evidence": None},
            payment_gateway=gateway,
        )
    )

    quote = client.get("/api/agent/products/refinery-utilization-evidence/quote")
    evidence = client.get("/api/agent/products/refinery-utilization-evidence/evidence")

    assert quote.status_code == 200
    assert quote.json()["price"] is None
    assert quote.json()["payment_enforcement"] == "not_configured"
    assert quote.json()["payment_protocols"] == []
    assert evidence.status_code == 200
    assert gateway.challenges == []
    assert gateway.verifications == []
    assert list_paid_fulfillments(data_dir / "metadata.sqlite") == []


def test_payment_operation_id_changes_with_price_terms() -> None:
    evidence_sha256 = "a" * 64
    cheap = build_payment_requirement(
        sku="fact-us-crude-stocks",
        amount=Decimal("0.0050"),
        currency="usd",
        evidence_sha256=evidence_sha256,
        description="fact",
    )
    same_terms = build_payment_requirement(
        sku="fact-us-crude-stocks",
        amount=Decimal("0.005"),
        currency="USD",
        evidence_sha256=evidence_sha256,
        description="fact",
    )
    expensive = build_payment_requirement(
        sku="fact-us-crude-stocks",
        amount=Decimal("0.006"),
        currency="USD",
        evidence_sha256=evidence_sha256,
        description="fact",
    )

    assert cheap.external_id == same_terms.external_id
    assert cheap.external_id != expensive.external_id
    assert cheap.external_id.endswith(evidence_sha256)
    assert ":USD:0.005:sha256:" in cheap.external_id
