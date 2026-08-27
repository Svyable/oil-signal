from pathlib import Path

from fastapi.testclient import TestClient
from oilsignal.api.app import _deterministic_answer, create_app
from oilsignal.data_ingestion.fixtures import FixtureIngestor, load_observations

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


def test_deterministic_answer_routes_demand_questions_to_product_supplied(data_dir: Path) -> None:
    result = FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    observations = load_observations(result.parquet_path)
    source_rows = [row for row in observations if row.series_id == "PET.DISTP2.W"][-2:]
    demand_rows = [
        row.model_copy(
            update={
                "series_id": "PET.DISTPSUS.W",
                "metric": "product_supplied",
                "product": "distillate fuel oil",
                "geography": "US",
                "unit": "thousand barrels per day",
                "value": 4100.0 + index * 100.0,
            }
        )
        for index, row in enumerate(source_rows)
    ]

    response = _deterministic_answer(
        "Is distillate demand rising this week?",
        [*observations, *demand_rows],
    )

    assert "U.S. distillate product supplied" in response.answer
    assert response.evidence
    assert all(citation.series_id == "PET.DISTPSUS.W" for citation in response.evidence)
