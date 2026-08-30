from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from oilsignal.agent.buyer import OilSignalBuyer
from oilsignal.agent.manifest import (
    AgentManifestEntry,
    build_change_manifest,
)
from oilsignal.api.app import create_app
from oilsignal.data_ingestion.fixtures import FixtureIngestor

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


def test_manifest_matches_product_state_and_revalidates(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    client = TestClient(
        create_app(
            data_dir,
            agent_sku_prices={"weekly-petroleum-delta": Decimal("0.02")},
        )
    )

    response = client.get("/api/agent/manifest")

    assert response.status_code == 200
    manifest = response.json()
    assert [row["sku"] for row in manifest["products"]] == sorted(
        row["sku"] for row in manifest["products"]
    )
    assert response.headers["x-oilsignal-manifest-sha256"] == manifest["manifest_sha256"]
    assert response.headers["etag"] == f'W/"sha256:{manifest["manifest_sha256"]}"'

    delta = next(row for row in manifest["products"] if row["sku"] == "weekly-petroleum-delta")
    state = client.get(delta["state_path"]).json()
    assert delta["availability"] == "available"
    assert delta["state_sha256"] == state["state_sha256"]
    assert delta["evidence_sha256"] == state["evidence_sha256"]
    assert delta["price"]["amount"] == "0.02"

    cached = client.get(
        "/api/agent/manifest",
        headers={"If-None-Match": response.headers["etag"]},
    )
    assert cached.status_code == 304
    assert cached.content == b""
    assert cached.headers["etag"] == response.headers["etag"]


def test_price_only_change_updates_manifest_and_state_not_evidence(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    first_client = TestClient(
        create_app(
            data_dir,
            agent_sku_prices={"weekly-petroleum-delta": Decimal("0.02")},
        )
    )
    second_client = TestClient(
        create_app(
            data_dir,
            agent_sku_prices={"weekly-petroleum-delta": Decimal("0.03")},
        )
    )

    first = OilSignalBuyer("http://testserver", client=first_client).poll_manifest().manifest
    second = OilSignalBuyer("http://testserver", client=second_client).poll_manifest().manifest
    assert first is not None
    assert second is not None

    first_delta = first.entry("weekly-petroleum-delta")
    second_delta = second.entry("weekly-petroleum-delta")
    assert first.manifest_sha256 != second.manifest_sha256
    assert first_delta.evidence_sha256 == second_delta.evidence_sha256
    assert first_delta.state_sha256 != second_delta.state_sha256
    assert first_delta.price is not None
    assert second_delta.price is not None
    assert first_delta.price.amount == Decimal("0.02")
    assert second_delta.price.amount == Decimal("0.03")
    assert second.changed_skus_since(first) == ["weekly-petroleum-delta"]


def test_buyer_polls_manifest_with_etag(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    buyer = OilSignalBuyer("http://testserver", client=TestClient(create_app(data_dir)))

    first = buyer.poll_manifest()
    assert first.manifest is not None
    cached = buyer.poll_manifest(etag=first.etag)

    assert first.not_modified is False
    assert cached.not_modified is True
    assert cached.manifest is None
    assert cached.etag == first.etag


def test_manifest_diff_detects_removed_products() -> None:
    first = build_change_manifest(
        [
            AgentManifestEntry(
                sku="a",
                name="A",
                product_kind="fact",
                state_path="/a/state",
                evidence_path="/a/evidence",
                quote_path="/a/quote",
                availability="available",
            ),
            AgentManifestEntry(
                sku="b",
                name="B",
                product_kind="fact",
                state_path="/b/state",
                evidence_path="/b/evidence",
                quote_path="/b/quote",
                availability="available",
            ),
        ]
    )
    second = build_change_manifest([first.entry("a")])

    assert second.changed_skus_since(first) == ["b"]
