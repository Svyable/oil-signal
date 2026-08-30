from __future__ import annotations

import json
from hashlib import sha256

from pydantic import BaseModel, Field

from oilsignal.agent.products import AgentPrice, AgentProduct
from oilsignal.agent.state import AgentProductState

MANIFEST_SCHEMA_VERSION = "1.0"


class AgentManifestEntry(BaseModel):
    sku: str
    name: str
    product_kind: str
    state_path: str
    evidence_path: str
    quote_path: str
    availability: str
    reason: str | None = None
    as_of: str | None = None
    state_sha256: str | None = None
    evidence_sha256: str | None = None
    fulfillment_available: bool = False
    available_for_purchase: bool = False
    price: AgentPrice | None = None
    payment_enforcement: str = "not_configured"
    payment_protocols: list[str] = Field(default_factory=list)


class AgentChangeManifest(BaseModel):
    schema_version: str = MANIFEST_SCHEMA_VERSION
    service: str = "OilSignal"
    products: list[AgentManifestEntry]
    manifest_sha256: str

    def entry(self, sku: str) -> AgentManifestEntry:
        for product in self.products:
            if product.sku == sku:
                return product
        raise KeyError(sku)

    def changed_skus_since(self, previous: AgentChangeManifest) -> list[str]:
        current_by_sku = {entry.sku: entry for entry in self.products}
        previous_by_sku = {entry.sku: entry for entry in previous.products}
        return sorted(
            sku
            for sku in current_by_sku.keys() | previous_by_sku.keys()
            if current_by_sku.get(sku) != previous_by_sku.get(sku)
        )


def available_manifest_entry(
    product: AgentProduct,
    state: AgentProductState,
) -> AgentManifestEntry:
    return AgentManifestEntry(
        sku=product.sku,
        name=product.name,
        product_kind=product.product_kind,
        state_path=product.state_path,
        evidence_path=product.evidence_path,
        quote_path=product.quote_path,
        availability="available" if state.fulfillment_available else "stale",
        as_of=state.as_of,
        state_sha256=state.state_sha256,
        evidence_sha256=state.evidence_sha256,
        fulfillment_available=state.fulfillment_available,
        available_for_purchase=state.available_for_purchase,
        price=state.price,
        payment_enforcement=state.payment_enforcement,
        payment_protocols=state.payment_protocols,
    )


def unavailable_manifest_entry(product: AgentProduct, reason: str) -> AgentManifestEntry:
    return AgentManifestEntry(
        sku=product.sku,
        name=product.name,
        product_kind=product.product_kind,
        state_path=product.state_path,
        evidence_path=product.evidence_path,
        quote_path=product.quote_path,
        availability="unavailable",
        reason=reason,
    )


def build_change_manifest(entries: list[AgentManifestEntry]) -> AgentChangeManifest:
    ordered = sorted(entries, key=lambda item: item.sku)
    semantics = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "service": "OilSignal",
        "products": [entry.model_dump(mode="json") for entry in ordered],
    }
    return AgentChangeManifest(
        products=ordered,
        manifest_sha256=_fingerprint(semantics),
    )


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode()
    return sha256(encoded).hexdigest()
