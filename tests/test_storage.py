from pathlib import Path

from oilsignal.data_ingestion.fixtures import FixtureIngestor
from oilsignal.storage.catalog import ObservationCatalog


FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


def test_duckdb_catalog_queries_normalized_parquet(data_dir: Path) -> None:
    result = FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    catalog = ObservationCatalog(result.parquet_path)

    latest = catalog.latest("PET.DISTP2.W")
    summary = catalog.series_summary()

    assert latest is not None
    assert latest["value"] == 26_900
    assert str(latest["observation_date"]) == "2026-08-21"
    assert {row["series_id"] for row in summary} == {
        "PET.CRDUUS.W",
        "PET.DISTP2.W",
        "PET.UTILUS.W",
    }
