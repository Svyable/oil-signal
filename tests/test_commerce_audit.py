from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from oilsignal.agent.commerce import build_payment_requirement, VerifiedPayment
from oilsignal.storage.commerce import list_paid_fulfillments, record_paid_fulfillment


def _requirement(digest: str = "a" * 64):
    return build_payment_requirement(
        sku="weekly-petroleum-evidence",
        amount=Decimal("0.05"),
        currency="USD",
        evidence_sha256=digest,
        description="Weekly petroleum evidence",
    )


def _verified(requirement, *, reference: str | None = "pay_123", payer: str | None = "agent-7"):
    return VerifiedPayment(
        protocol="x402-v2",
        response_headers={"PAYMENT-RESPONSE": "opaque-receipt"},
        external_id=requirement.external_id,
        reference=reference,
        payer=payer,
    )


def test_paid_fulfillment_audit_is_append_only_and_filterable(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.sqlite"
    requirement = _requirement()
    verified = _verified(requirement)
    first_at = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)
    second_at = first_at + timedelta(minutes=1)

    first = record_paid_fulfillment(
        metadata_path,
        requirement=requirement,
        verified=verified,
        fulfilled_at=first_at,
    )
    second = record_paid_fulfillment(
        metadata_path,
        requirement=requirement,
        verified=verified,
        fulfilled_at=second_at,
    )

    assert first.id != second.id
    rows = list_paid_fulfillments(metadata_path, external_id=requirement.external_id)
    assert [row.id for row in rows] == [second.id, first.id]
    assert all(row.gateway_reference == "pay_123" for row in rows)
    assert all(row.payer == "agent-7" for row in rows)
    assert all(row.amount == Decimal("0.05") for row in rows)
    assert all(row.fulfilled_at.tzinfo is not None for row in rows)

    by_reference = list_paid_fulfillments(metadata_path, gateway_reference="pay_123")
    assert len(by_reference) == 2
    assert list_paid_fulfillments(metadata_path, gateway_reference="missing") == []


def test_paid_fulfillment_audit_does_not_persist_protocol_headers(tmp_path: Path) -> None:
    requirement = _requirement()
    verified = _verified(requirement)

    row = record_paid_fulfillment(
        tmp_path / "metadata.sqlite",
        requirement=requirement,
        verified=verified,
    )

    dumped = row.model_dump(mode="json")
    assert "response_headers" not in dumped
    assert "PAYMENT-RESPONSE" not in str(dumped)
    assert "opaque-receipt" not in str(dumped)


def test_paid_fulfillment_audit_rejects_mismatched_or_naive_receipts(tmp_path: Path) -> None:
    requirement = _requirement()
    mismatch = VerifiedPayment(
        protocol="x402-v2",
        response_headers={},
        external_id="oilsignal:other:sha256:" + "b" * 64,
    )

    with pytest.raises(ValueError, match="does not match"):
        record_paid_fulfillment(
            tmp_path / "metadata.sqlite",
            requirement=requirement,
            verified=mismatch,
        )

    naive = datetime(2026, 8, 29, 9, 0, tzinfo=UTC).replace(tzinfo=None)
    with pytest.raises(ValueError, match="timezone-aware"):
        record_paid_fulfillment(
            tmp_path / "metadata.sqlite",
            requirement=requirement,
            verified=_verified(requirement),
            fulfilled_at=naive,
        )


def test_paid_fulfillment_audit_validates_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="limit"):
        list_paid_fulfillments(tmp_path / "metadata.sqlite", limit=0)
