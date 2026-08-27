from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from oilsignal.storage.metadata import list_alert_outbox, save_alert_outbox


class OutboxDeliveryAdapter(Protocol):
    name: str

    def send(self, payload_json: str) -> None: ...


class ConsoleOutboxDelivery:
    name = "console"

    def send(self, payload_json: str) -> None:
        print(payload_json)


class DeliveryReceipt(BaseModel):
    outbox_id: str
    policy_id: str
    adapter: str
    status: str
    attempts: int
    attempted_at: datetime
    delivered_at: datetime | None = None
    error: str | None = None


def flush_alert_outbox(
    metadata_path: Path,
    adapter: OutboxDeliveryAdapter,
    *,
    limit: int = 100,
) -> list[DeliveryReceipt]:
    """Attempt pending/failed deliveries once, returning an auditable receipt per row."""

    receipts: list[DeliveryReceipt] = []
    for row in list_alert_outbox(metadata_path, limit=limit):
        attempted_at = datetime.now(UTC)
        row.adapter = adapter.name
        row.attempts += 1
        row.last_attempt_at = attempted_at
        error: str | None = None
        delivered_at: datetime | None = None
        try:
            adapter.send(row.payload_json)
        except Exception as exc:
            row.status = "failed"
            error = str(exc)[:1000] or exc.__class__.__name__
            row.last_error = error
        else:
            row.status = "delivered"
            delivered_at = datetime.now(UTC)
            row.delivered_at = delivered_at
            row.last_error = None
        save_alert_outbox(metadata_path, row)
        receipts.append(
            DeliveryReceipt(
                outbox_id=row.id,
                policy_id=row.policy_id,
                adapter=adapter.name,
                status=row.status,
                attempts=row.attempts,
                attempted_at=attempted_at,
                delivered_at=delivered_at,
                error=error,
            )
        )
    return receipts
