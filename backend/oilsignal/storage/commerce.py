from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlmodel import Field, Session, SQLModel, col, select

from oilsignal.agent.commerce import PaymentRequirement, VerifiedPayment
from oilsignal.storage.metadata import create_metadata_engine


class PaidFulfillmentRow(SQLModel, table=True):
    """Append-only audit event for a successfully verified paid Evidence Pack fulfillment."""

    id: str = Field(primary_key=True)
    fulfilled_at: datetime = Field(index=True)
    external_id: str = Field(index=True)
    sku: str = Field(index=True)
    evidence_sha256: str = Field(index=True)
    amount: Decimal
    currency: str
    resource_path: str
    protocol: str = Field(index=True)
    gateway_reference: str | None = Field(default=None, index=True)
    payer: str | None = None


def record_paid_fulfillment(
    path: Path,
    *,
    requirement: PaymentRequirement,
    verified: VerifiedPayment,
    fulfilled_at: datetime | None = None,
) -> PaidFulfillmentRow:
    """Persist one fulfilled-response event without storing credentials or receipt headers."""

    if verified.external_id != requirement.external_id:
        raise ValueError("verified payment does not match the evidence requirement")
    now = fulfilled_at or datetime.now(UTC)
    _require_aware(now)
    row = PaidFulfillmentRow(
        id=f"ful_{uuid4().hex}",
        fulfilled_at=now.astimezone(UTC),
        external_id=requirement.external_id,
        sku=requirement.sku,
        evidence_sha256=requirement.evidence_sha256,
        amount=requirement.amount,
        currency=requirement.currency,
        resource_path=requirement.resource_path,
        protocol=verified.protocol,
        gateway_reference=verified.reference,
        payer=verified.payer,
    )
    engine = create_metadata_engine(path)
    with Session(engine, expire_on_commit=False) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        return _copy_paid_fulfillment(row)


def list_paid_fulfillments(
    path: Path,
    *,
    external_id: str | None = None,
    gateway_reference: str | None = None,
    sku: str | None = None,
    limit: int = 100,
) -> list[PaidFulfillmentRow]:
    """List newest fulfillment audit events with optional reconciliation filters."""

    if limit < 1:
        raise ValueError("fulfillment audit limit must be positive")
    engine = create_metadata_engine(path)
    with Session(engine) as session:
        statement = select(PaidFulfillmentRow)
        if external_id is not None:
            statement = statement.where(PaidFulfillmentRow.external_id == external_id)
        if gateway_reference is not None:
            statement = statement.where(PaidFulfillmentRow.gateway_reference == gateway_reference)
        if sku is not None:
            statement = statement.where(PaidFulfillmentRow.sku == sku)
        statement = statement.order_by(
            col(PaidFulfillmentRow.fulfilled_at).desc(),
            col(PaidFulfillmentRow.id).desc(),
        ).limit(limit)
        return [_copy_paid_fulfillment(row) for row in session.exec(statement).all()]


def _copy_paid_fulfillment(row: PaidFulfillmentRow) -> PaidFulfillmentRow:
    return row.model_copy(update={"fulfilled_at": _as_utc(row.fulfilled_at)})


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("fulfillment audit timestamps must be timezone-aware")
