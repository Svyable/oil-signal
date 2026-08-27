from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, col, create_engine, select


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


class AlertStateRow(SQLModel, table=True):
    policy_id: str = Field(primary_key=True)
    active: bool = False
    last_changed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_triggered_at: datetime | None = None
    last_as_of: str | None = None


class AlertOutboxRow(SQLModel, table=True):
    id: str = Field(primary_key=True)
    policy_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    as_of: str | None = None
    payload_json: str
    status: str = Field(default="pending", index=True)
    adapter: str | None = None
    attempts: int = 0
    last_attempt_at: datetime | None = None
    delivered_at: datetime | None = None
    last_error: str | None = None


def create_metadata_engine(path: Path) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    return engine


def get_ingestion_run(path: Path, run_id: str) -> IngestionRunRow | None:
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        return session.exec(select(IngestionRunRow).where(IngestionRunRow.id == run_id)).first()


def get_ingestion_run_for_parquet(path: Path, parquet_path: Path) -> IngestionRunRow | None:
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        return session.exec(
            select(IngestionRunRow).where(IngestionRunRow.parquet_path == str(parquet_path))
        ).first()


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


def get_alert_state(path: Path, policy_id: str) -> AlertStateRow | None:
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        return session.exec(select(AlertStateRow).where(AlertStateRow.policy_id == policy_id)).first()


def save_alert_state(path: Path, row: AlertStateRow) -> None:
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        session.merge(row)
        session.commit()


def save_alert_transition(
    path: Path,
    state: AlertStateRow,
    outbox: AlertOutboxRow | None,
) -> None:
    """Persist alert state and its notification enqueue in one transaction."""

    engine = create_metadata_engine(path)
    with Session(engine) as session:
        session.merge(state)
        if outbox is not None:
            session.add(outbox)
        session.commit()


def get_alert_outbox(path: Path, outbox_id: str) -> AlertOutboxRow | None:
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        return session.exec(select(AlertOutboxRow).where(AlertOutboxRow.id == outbox_id)).first()


def list_alert_outbox(path: Path, limit: int = 100) -> list[AlertOutboxRow]:
    if limit < 1:
        raise ValueError("outbox limit must be positive")
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        statement = (
            select(AlertOutboxRow)
            .where(AlertOutboxRow.status != "delivered")
            .order_by(col(AlertOutboxRow.created_at), col(AlertOutboxRow.id))
            .limit(limit)
        )
        return list(session.exec(statement).all())


def save_alert_outbox(path: Path, row: AlertOutboxRow) -> None:
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        session.merge(row)
        session.commit()


def row_to_dict(row: SQLModel) -> dict[str, Any]:
    return row.model_dump()
