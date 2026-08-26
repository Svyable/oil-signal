from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Field, Session, SQLModel, create_engine


class IngestionRunRow(SQLModel, table=True):
    id: str = Field(primary_key=True)
    source: str
    started_at: datetime
    completed_at: datetime | None = None
    status: str = "running"
    rows_written: int = 0
    raw_path: str | None = None
    parquet_path: str | None = None


class ReportRunRow(SQLModel, table=True):
    id: str = Field(primary_key=True)
    report_type: str
    as_of: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    output_format: str


def create_metadata_engine(path: Path):  # type: ignore[no-untyped-def]
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    return engine


def save_ingestion_run(path: Path, row: IngestionRunRow) -> None:
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        session.add(row)
        session.commit()
