from __future__ import annotations

import argparse
from pathlib import Path

from oilsignal.config import settings
from oilsignal.data_ingestion.fixtures import FixtureIngestor


def main() -> None:
    parser = argparse.ArgumentParser(description="Load synthetic offline petroleum fixtures")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("tests/fixtures/petroleum_weekly.csv"),
    )
    parser.add_argument("--if-empty", action="store_true")
    args = parser.parse_args()
    if args.if_empty and any(settings.parquet_dir.glob("*.parquet")):
        print("OilSignal data directory already contains Parquet observations; skipping fixture.")
        return
    result = FixtureIngestor(settings.data_dir).ingest_csv(args.fixture)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
