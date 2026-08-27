from pathlib import Path

from fastapi.testclient import TestClient
from oilsignal.api.app import create_app
from oilsignal.data_ingestion.fixtures import FixtureIngestor

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


def test_readiness_fails_closed_without_data_and_reports_dataset_when_ready(
    data_dir: Path,
) -> None:
    client = TestClient(create_app(data_dir))

    empty = client.get("/health/ready")
    assert empty.status_code == 503
    assert empty.json()["data_available"] is False

    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    ready = client.get("/health/ready")

    assert ready.status_code == 200
    payload = ready.json()
    assert payload["status"] == "ready"
    assert payload["series_count"] >= 1
    assert payload["latest_observation"]
