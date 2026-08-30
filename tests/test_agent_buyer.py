from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from oilsignal.agent.buyer import (
    BuyerIntegrityError,
    BuyerPaymentRequired,
    OilSignalBuyer,
)
from oilsignal.agent.pilot_gateway import PILOT_CREDENTIAL_HEADER, PilotAccessGateway
from oilsignal.api.app import create_app
from oilsignal.data_ingestion.fixtures import FixtureIngestor
from oilsignal.storage.commerce import list_paid_fulfillments

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"
PILOT_KEY = "buyer_" + "a" * 40


def test_buyer_discovers_quotes_and_revalidates_product_state(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    app_client = TestClient(create_app(data_dir, agent_unit_price_usd=Decimal("0.02")))
    buyer = OilSignalBuyer("http://testserver", client=app_client)

    catalog = buyer.catalog()
    quote = buyer.quote("weekly-petroleum-delta")
    first = buyer.poll_state("weekly-petroleum-delta")
    assert first.state is not None
    cached = buyer.poll_state("weekly-petroleum-delta", etag=first.etag)

    assert any(product.sku == "weekly-petroleum-delta" for product in catalog.products)
    assert quote.price is not None
    assert quote.price.amount == Decimal("0.02")
    assert first.not_modified is False
    assert first.etag == f'W/"sha256:{first.state.state_sha256}"'
    assert cached.not_modified is True
    assert cached.state is None
    assert cached.etag == first.etag


def test_buyer_surfaces_402_then_fulfills_and_verifies_exact_state_digest(
    data_dir: Path,
) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    gateway = PilotAccessGateway(
        PILOT_KEY,
        customer="agent-buyer",
        allowed_skus=frozenset({"weekly-petroleum-delta"}),
        reference="pilot-buyer-001",
    )
    app_client = TestClient(
        create_app(
            data_dir,
            agent_sku_prices={"weekly-petroleum-delta": Decimal("0.02")},
            payment_gateway=gateway,
        )
    )
    buyer = OilSignalBuyer("http://testserver", client=app_client)
    state_result = buyer.poll_state("weekly-petroleum-delta")
    assert state_result.state is not None
    state = state_result.state

    with pytest.raises(BuyerPaymentRequired) as exc_info:
        buyer.fetch_evidence(
            "weekly-petroleum-delta",
            expected_evidence_sha256=state.evidence_sha256,
        )

    challenge = exc_info.value
    assert challenge.problem.sku == "weekly-petroleum-delta"
    assert challenge.problem.amount == Decimal("0.02")
    assert challenge.problem.evidence_sha256 == state.evidence_sha256
    assert challenge.headers["x-oilsignal-pilot-required"] == PILOT_CREDENTIAL_HEADER

    fulfilled = buyer.fetch_evidence(
        "weekly-petroleum-delta",
        credential_headers={PILOT_CREDENTIAL_HEADER: PILOT_KEY},
        expected_evidence_sha256=state.evidence_sha256,
    )

    assert fulfilled.not_modified is False
    assert fulfilled.evidence is not None
    assert fulfilled.evidence.evidence_sha256 == state.evidence_sha256
    assert fulfilled.etag == f'W/"sha256:{state.evidence_sha256}"'

    audits = list_paid_fulfillments(data_dir / "metadata.sqlite")
    assert len(audits) == 1
    assert audits[0].gateway_reference == "pilot-buyer-001"
    assert audits[0].evidence_sha256 == state.evidence_sha256


def test_buyer_free_evidence_revalidation_uses_evidence_etag(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    buyer = OilSignalBuyer("http://testserver", client=TestClient(create_app(data_dir)))

    first = buyer.fetch_evidence("fact-us-crude-stocks")
    cached = buyer.fetch_evidence("fact-us-crude-stocks", etag=first.etag)

    assert first.evidence is not None
    assert first.not_modified is False
    assert cached.not_modified is True
    assert cached.evidence is None
    assert cached.etag == first.etag


def test_buyer_rejects_fulfillment_that_differs_from_polled_state(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    buyer = OilSignalBuyer("http://testserver", client=TestClient(create_app(data_dir)))

    with pytest.raises(BuyerIntegrityError, match="does not match the digest observed"):
        buyer.fetch_evidence(
            "fact-us-crude-stocks",
            expected_evidence_sha256="f" * 64,
        )
