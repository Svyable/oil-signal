from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256

from pydantic import BaseModel

from oilsignal.agent.products import AgentPrice, AgentQuote, EvidencePack
from oilsignal.freshness import DatasetFreshness, FreshnessState

PRODUCT_STATE_SCHEMA_VERSION = "1.0"


class AgentProductState(BaseModel):
    schema_version: str = PRODUCT_STATE_SCHEMA_VERSION
    sku: str
    title: str
    report_type: str
    as_of: str
    evidence_sha256: str
    data_source: str | None = None
    source_fetched_at: datetime | None = None
    freshness: DatasetFreshness
    fulfillment_available: bool
    available_for_purchase: bool
    price: AgentPrice | None = None
    fulfillment_path: str
    payment_enforcement: str
    payment_protocols: list[str]
    state_sha256: str


def build_agent_product_state(pack: EvidencePack, quote: AgentQuote) -> AgentProductState:
    if pack.sku != quote.sku:
        raise ValueError("product state requires matching evidence and quote SKUs")

    fulfillment_available = pack.freshness.status != FreshnessState.STALE
    semantics = {
        "schema_version": PRODUCT_STATE_SCHEMA_VERSION,
        "sku": pack.sku,
        "title": pack.title,
        "report_type": pack.report_type,
        "as_of": pack.as_of,
        "evidence_sha256": pack.evidence_sha256,
        "data_source": pack.data_source,
        "source_fetched_at": pack.source_fetched_at,
        "freshness": _freshness_semantics(pack.freshness),
        "fulfillment_available": fulfillment_available,
        "available_for_purchase": quote.available_for_purchase,
        "price": quote.price.model_dump(mode="json") if quote.price else None,
        "fulfillment_path": quote.fulfillment_path,
        "payment_enforcement": quote.payment_enforcement,
        "payment_protocols": quote.payment_protocols,
    }
    return AgentProductState(
        sku=pack.sku,
        title=pack.title,
        report_type=pack.report_type,
        as_of=pack.as_of,
        evidence_sha256=pack.evidence_sha256,
        data_source=pack.data_source,
        source_fetched_at=pack.source_fetched_at,
        freshness=pack.freshness,
        fulfillment_available=fulfillment_available,
        available_for_purchase=quote.available_for_purchase,
        price=quote.price,
        fulfillment_path=quote.fulfillment_path,
        payment_enforcement=quote.payment_enforcement,
        payment_protocols=quote.payment_protocols,
        state_sha256=_fingerprint(semantics),
    )


def _freshness_semantics(freshness: DatasetFreshness) -> dict[str, object]:
    return {
        "status": freshness.status.value,
        "latest_observation": (
            freshness.latest_observation.isoformat() if freshness.latest_observation else None
        ),
        "expected_week_ending": (
            freshness.expected_week_ending.isoformat() if freshness.expected_week_ending else None
        ),
        "stale_series": freshness.stale_series,
        "live_series_count": freshness.live_series_count,
    }


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode()
    return sha256(encoded).hexdigest()
