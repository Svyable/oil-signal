from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

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


class AlertDeliveryLeaseRow(SQLModel, table=True):
    outbox_id: str = Field(primary_key=True)
    worker_id: str = Field(index=True)
    adapter: str
    leased_at: datetime
    expires_at: datetime = Field(index=True)


class AlertRetryScheduleRow(SQLModel, table=True):
    outbox_id: str = Field(primary_key=True)
    retry_at: datetime = Field(index=True)


class AlertDeadLetterRow(SQLModel, table=True):
    id: str = Field(primary_key=True)
    outbox_id: str = Field(index=True)
    policy_id: str = Field(index=True)
    dead_lettered_at: datetime = Field(index=True)
    attempts: int
    reason: str
    payload_json: str
    requeued_at: datetime | None = Field(default=None, index=True)


class AlertLeaseLostError(RuntimeError):
    """Raised when a worker tries to acknowledge an expired or stolen delivery lease."""


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
        row = session.exec(select(AlertOutboxRow).where(AlertOutboxRow.id == outbox_id)).first()
        return _copy_alert_outbox(row) if row else None


def get_alert_delivery_lease(path: Path, outbox_id: str) -> AlertDeliveryLeaseRow | None:
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        row = session.exec(
            select(AlertDeliveryLeaseRow).where(AlertDeliveryLeaseRow.outbox_id == outbox_id)
        ).first()
        return _copy_alert_lease(row) if row else None


def get_alert_retry_schedule(path: Path, outbox_id: str) -> AlertRetryScheduleRow | None:
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        row = session.exec(
            select(AlertRetryScheduleRow).where(AlertRetryScheduleRow.outbox_id == outbox_id)
        ).first()
        return _copy_retry_schedule(row) if row else None


def list_alert_outbox(path: Path, limit: int = 100) -> list[AlertOutboxRow]:
    if limit < 1:
        raise ValueError("outbox limit must be positive")
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        statement = (
            select(AlertOutboxRow)
            .where(col(AlertOutboxRow.status).in_(["pending", "failed", "in_flight"]))
            .order_by(col(AlertOutboxRow.created_at), col(AlertOutboxRow.id))
            .limit(limit)
        )
        return [_copy_alert_outbox(row) for row in session.exec(statement).all()]


def save_alert_outbox(path: Path, row: AlertOutboxRow) -> None:
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        session.merge(row)
        session.commit()


def claim_alert_outbox(
    path: Path,
    *,
    worker_id: str,
    adapter: str,
    now: datetime,
    lease_seconds: int,
    max_attempts: int,
    base_backoff_seconds: int,
    max_backoff_seconds: int,
) -> AlertOutboxRow | None:
    """Atomically claim one eligible outbox row for a worker.

    SQLite's BEGIN IMMEDIATE serializes the short claim transaction. External delivery happens
    after the transaction, so slow providers never hold the database write lock.
    """

    _validate_delivery_policy(
        lease_seconds=lease_seconds,
        max_attempts=max_attempts,
        base_backoff_seconds=base_backoff_seconds,
        max_backoff_seconds=max_backoff_seconds,
    )
    _require_aware(now)
    now = now.astimezone(UTC)
    engine = create_metadata_engine(path)
    connection = engine.connect()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        expired = session.exec(
            select(AlertDeliveryLeaseRow).where(AlertDeliveryLeaseRow.expires_at <= now)
        ).all()
        for lease in expired:
            session.delete(lease)

        active_leases = session.exec(select(AlertDeliveryLeaseRow)).all()
        leased_ids = {lease.outbox_id for lease in active_leases}
        retry_schedules = {
            schedule.outbox_id: schedule
            for schedule in session.exec(select(AlertRetryScheduleRow)).all()
        }
        candidates = session.exec(
            select(AlertOutboxRow)
            .where(col(AlertOutboxRow.status).in_(["pending", "failed", "in_flight"]))
            .order_by(col(AlertOutboxRow.created_at), col(AlertOutboxRow.id))
        ).all()

        for row in candidates:
            if row.id in leased_ids:
                continue
            if row.attempts >= max_attempts:
                _dead_letter_in_session(
                    session,
                    row,
                    now,
                    reason=row.last_error or "delivery attempt budget exhausted",
                )
                continue

            retry_schedule = retry_schedules.get(row.id)
            if retry_schedule is not None:
                if _as_utc(retry_schedule.retry_at) > now:
                    continue
                session.delete(retry_schedule)

            if not _retry_is_due(
                row,
                now=now,
                base_backoff_seconds=base_backoff_seconds,
                max_backoff_seconds=max_backoff_seconds,
            ):
                continue

            row.status = "in_flight"
            row.adapter = adapter
            row.attempts += 1
            row.last_attempt_at = now
            session.add(
                AlertDeliveryLeaseRow(
                    outbox_id=row.id,
                    worker_id=worker_id,
                    adapter=adapter,
                    leased_at=now,
                    expires_at=now + timedelta(seconds=lease_seconds),
                )
            )
            session.flush()
            claimed = _copy_alert_outbox(row)
            connection.commit()
            return claimed

        session.flush()
        connection.commit()
        return None
    except Exception:
        connection.rollback()
        raise
    finally:
        session.close()
        connection.close()


def complete_alert_delivery(
    path: Path,
    *,
    outbox_id: str,
    worker_id: str,
    now: datetime,
    delivered: bool,
    max_attempts: int,
    error: str | None = None,
    permanent_failure: bool = False,
    retry_at: datetime | None = None,
) -> AlertOutboxRow:
    """Acknowledge a claimed delivery only if the worker still owns a live lease."""

    _require_aware(now)
    now = now.astimezone(UTC)
    if retry_at is not None:
        _require_aware(retry_at)
        retry_at = retry_at.astimezone(UTC)
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    engine = create_metadata_engine(path)
    connection = engine.connect()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        lease = session.exec(
            select(AlertDeliveryLeaseRow).where(AlertDeliveryLeaseRow.outbox_id == outbox_id)
        ).first()
        if (
            lease is None
            or lease.worker_id != worker_id
            or _as_utc(lease.expires_at) <= now
        ):
            raise AlertLeaseLostError(f"delivery lease is no longer owned by {worker_id}")

        row = session.exec(select(AlertOutboxRow).where(AlertOutboxRow.id == outbox_id)).first()
        if row is None:
            raise ValueError(f"outbox row not found: {outbox_id}")

        if delivered:
            row.status = "delivered"
            row.delivered_at = now
            row.last_error = None
            _delete_retry_schedule_in_session(session, outbox_id)
        else:
            bounded_error = (error or "delivery failed")[:1000]
            row.last_error = bounded_error
            if permanent_failure or row.attempts >= max_attempts:
                _dead_letter_in_session(session, row, now, reason=bounded_error)
            else:
                row.status = "failed"
                _delete_retry_schedule_in_session(session, outbox_id)
                if retry_at is not None:
                    session.add(AlertRetryScheduleRow(outbox_id=outbox_id, retry_at=retry_at))
        session.delete(lease)
        session.flush()
        completed = _copy_alert_outbox(row)
        connection.commit()
        return completed
    except Exception:
        connection.rollback()
        raise
    finally:
        session.close()
        connection.close()


def list_alert_dead_letters(
    path: Path,
    *,
    active_only: bool = True,
    limit: int = 100,
) -> list[AlertDeadLetterRow]:
    if limit < 1:
        raise ValueError("dead-letter limit must be positive")
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        statement = select(AlertDeadLetterRow)
        if active_only:
            statement = statement.where(col(AlertDeadLetterRow.requeued_at).is_(None))
        statement = statement.order_by(col(AlertDeadLetterRow.dead_lettered_at).desc()).limit(limit)
        return [_copy_dead_letter(row) for row in session.exec(statement).all()]


def requeue_alert_dead_letter(
    path: Path,
    *,
    outbox_id: str,
    now: datetime,
) -> AlertOutboxRow:
    """Re-arm a dead-lettered notification with a fresh attempt budget."""

    _require_aware(now)
    now = now.astimezone(UTC)
    engine = create_metadata_engine(path)
    connection = engine.connect()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        row = session.exec(select(AlertOutboxRow).where(AlertOutboxRow.id == outbox_id)).first()
        if row is None:
            raise ValueError(f"outbox row not found: {outbox_id}")
        if row.status != "dead_letter":
            raise ValueError(f"outbox row is not dead-lettered: {outbox_id}")
        lease = session.exec(
            select(AlertDeliveryLeaseRow).where(AlertDeliveryLeaseRow.outbox_id == outbox_id)
        ).first()
        if lease is not None:
            session.delete(lease)
        _delete_retry_schedule_in_session(session, outbox_id)

        dead_letter = session.exec(
            select(AlertDeadLetterRow)
            .where(AlertDeadLetterRow.outbox_id == outbox_id)
            .where(col(AlertDeadLetterRow.requeued_at).is_(None))
            .order_by(col(AlertDeadLetterRow.dead_lettered_at).desc())
        ).first()
        if dead_letter is not None:
            dead_letter.requeued_at = now

        row.status = "pending"
        row.adapter = None
        row.attempts = 0
        row.last_attempt_at = None
        row.delivered_at = None
        row.last_error = None
        session.flush()
        requeued = _copy_alert_outbox(row)
        connection.commit()
        return requeued
    except Exception:
        connection.rollback()
        raise
    finally:
        session.close()
        connection.close()


def _retry_is_due(
    row: AlertOutboxRow,
    *,
    now: datetime,
    base_backoff_seconds: int,
    max_backoff_seconds: int,
) -> bool:
    if row.last_attempt_at is None or row.attempts == 0:
        return True
    exponent = max(row.attempts - 1, 0)
    delay = min(base_backoff_seconds * (2**exponent), max_backoff_seconds)
    return now >= _as_utc(row.last_attempt_at) + timedelta(seconds=delay)


def _dead_letter_in_session(
    session: Session,
    row: AlertOutboxRow,
    now: datetime,
    *,
    reason: str,
) -> None:
    _delete_retry_schedule_in_session(session, row.id)
    row.status = "dead_letter"
    row.last_error = reason[:1000]
    session.add(
        AlertDeadLetterRow(
            id=f"dl_{uuid4().hex}",
            outbox_id=row.id,
            policy_id=row.policy_id,
            dead_lettered_at=now,
            attempts=row.attempts,
            reason=reason[:1000],
            payload_json=row.payload_json,
        )
    )


def _delete_retry_schedule_in_session(session: Session, outbox_id: str) -> None:
    schedule = session.exec(
        select(AlertRetryScheduleRow).where(AlertRetryScheduleRow.outbox_id == outbox_id)
    ).first()
    if schedule is not None:
        session.delete(schedule)


def _validate_delivery_policy(
    *,
    lease_seconds: int,
    max_attempts: int,
    base_backoff_seconds: int,
    max_backoff_seconds: int,
) -> None:
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    if base_backoff_seconds < 0 or max_backoff_seconds < 0:
        raise ValueError("backoff values cannot be negative")
    if max_backoff_seconds < base_backoff_seconds:
        raise ValueError("max_backoff_seconds cannot be smaller than base_backoff_seconds")


def _copy_alert_outbox(row: AlertOutboxRow) -> AlertOutboxRow:
    data = row.model_dump()
    for field_name in ("created_at", "last_attempt_at", "delivered_at"):
        value = data.get(field_name)
        if isinstance(value, datetime):
            data[field_name] = _as_utc(value)
    return AlertOutboxRow.model_validate(data)


def _copy_alert_lease(row: AlertDeliveryLeaseRow) -> AlertDeliveryLeaseRow:
    data = row.model_dump()
    for field_name in ("leased_at", "expires_at"):
        value = data.get(field_name)
        if isinstance(value, datetime):
            data[field_name] = _as_utc(value)
    return AlertDeliveryLeaseRow.model_validate(data)


def _copy_retry_schedule(row: AlertRetryScheduleRow) -> AlertRetryScheduleRow:
    data = row.model_dump()
    value = data.get("retry_at")
    if isinstance(value, datetime):
        data["retry_at"] = _as_utc(value)
    return AlertRetryScheduleRow.model_validate(data)


def _copy_dead_letter(row: AlertDeadLetterRow) -> AlertDeadLetterRow:
    data = row.model_dump()
    for field_name in ("dead_lettered_at", "requeued_at"):
        value = data.get(field_name)
        if isinstance(value, datetime):
            data[field_name] = _as_utc(value)
    return AlertDeadLetterRow.model_validate(data)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None:
        raise ValueError("delivery timestamps must be timezone-aware")


def row_to_dict(row: SQLModel) -> dict[str, Any]:
    return row.model_dump()
