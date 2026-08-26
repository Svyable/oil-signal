from pathlib import Path

from fastapi.testclient import TestClient
from oilsignal.api.app import create_app
from oilsignal.data_ingestion.fixtures import FixtureIngestor

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


def test_api_generates_weekly_report_with_citations(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    client = TestClient(create_app(data_dir))

    response = client.get("/api/reports/weekly")

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_type"] == "weekly_petroleum_brief"
    assert payload["sections"][0]["claims"][0]["citations"]


def test_ask_endpoint_returns_answer_and_evidence_table(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    client = TestClient(create_app(data_dir))

    response = client.post("/api/ask", json={"question": "Explain Midwest diesel tightness this week"})

    assert response.status_code == 200
    payload = response.json()
    assert "PADD 2 distillate" in payload["answer"]
    assert len(payload["evidence"]) == 2
    assert payload["evidence"][0]["series_id"] == "PET.DISTP2.W"
