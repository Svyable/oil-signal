from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, create_engine, select


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


def create_metadata_engine(path: Path) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    return engine


def get_ingestion_run(path: Path, run_id: str) -> IngestionRunRow | None:
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        return session.exec(select(IngestionRunRow).where(IngestionRunRow.id == run_id)).first()


def save_ingestion_run(path: Path, row: IngestionRunRow) -> None:
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        session.merge(row)
        session.commit()


def save_report_run(path: Path, row: ReportRunRow) -> None:
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        session.merge(row)
        session.commit()


def row_to_dict(row: SQLModel) -> dict[str, Any]:
    return row.model_dump()
