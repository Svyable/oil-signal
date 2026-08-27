from __future__ import annotations

import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from oilsignal.storage.metadata import (
    AlertLeaseLostError,
    claim_alert_outbox,
    complete_alert_delivery,
)


class OutboxDeliveryAdapter(Protocol):
    name: str

    def send(self, payload_json: str) -> None: ...


class ConsoleOutboxDelivery:
    name = "console"

    def send(self, payload_json: str) -> None:
        print(payload_json)


class DeliveryPolicy(BaseModel):
    lease_seconds: int = Field(default=120, ge=1)
    max_attempts: int = Field(default=5, ge=1)
    base_backoff_seconds: int = Field(default=30, ge=0)
    max_backoff_seconds: int = Field(default=3600, ge=0)

    @model_validator(mode="after")
    def validate_backoff(self) -> DeliveryPolicy:
        if self.max_backoff_seconds < self.base_backoff_seconds:
            raise ValueError("max_backoff_seconds cannot be smaller than base_backoff_seconds")
        return self


class DeliveryReceipt(BaseModel):
    outbox_id: str
    policy_id: str
    adapter: str
    worker_id: str
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
    worker_id: str | None = None,
    policy: DeliveryPolicy | None = None,
    now: datetime | None = None,
) -> list[DeliveryReceipt]:
    """Drain eligible outbox rows with leases, exponential backoff, and dead-lettering."""

    if limit < 1:
        raise ValueError("delivery limit must be positive")
    delivery_policy = policy or DeliveryPolicy()
    worker = worker_id or default_worker_id()
    receipts: list[DeliveryReceipt] = []

    for _ in range(limit):
        attempted_at = now or datetime.now(UTC)
        claimed = claim_alert_outbox(
            metadata_path,
            worker_id=worker,
            adapter=adapter.name,
            now=attempted_at,
            lease_seconds=delivery_policy.lease_seconds,
            max_attempts=delivery_policy.max_attempts,
            base_backoff_seconds=delivery_policy.base_backoff_seconds,
            max_backoff_seconds=delivery_policy.max_backoff_seconds,
        )
        if claimed is None:
            break

        error: str | None = None
        delivered = False
        try:
            adapter.send(claimed.payload_json)
            delivered = True
        except Exception as exc:
            error = str(exc)[:1000] or exc.__class__.__name__

        completed_at = now or datetime.now(UTC)
        try:
            completed = complete_alert_delivery(
                metadata_path,
                outbox_id=claimed.id,
                worker_id=worker,
                now=completed_at,
                delivered=delivered,
                max_attempts=delivery_policy.max_attempts,
                error=error,
            )
            status = completed.status
            delivered_at = completed.delivered_at
        except AlertLeaseLostError as exc:
            status = "lease_lost"
            delivered_at = None
            error = str(exc)

        receipts.append(
            DeliveryReceipt(
                outbox_id=claimed.id,
                policy_id=claimed.policy_id,
                adapter=adapter.name,
                worker_id=worker,
                status=status,
                attempts=claimed.attempts,
                attempted_at=attempted_at,
                delivered_at=delivered_at,
                error=error,
            )
        )
    return receipts


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
