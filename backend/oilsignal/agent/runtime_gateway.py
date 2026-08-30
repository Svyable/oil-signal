from __future__ import annotations

from oilsignal.agent.commerce import PaymentGateway
from oilsignal.agent.http_payment_gateway import build_configured_payment_gateway
from oilsignal.agent.pilot_gateway import PilotAccessGateway
from oilsignal.agent.products import product_exists
from oilsignal.config import Settings


def build_runtime_payment_gateway(settings: Settings) -> PaymentGateway | None:
    """Select exactly one runtime commerce gateway from operator configuration."""

    pilot_key = settings.agent_pilot_access_key
    pilot_skus_raw = settings.agent_pilot_skus.strip()
    pilot_reference = settings.agent_pilot_reference
    pilot_requested = pilot_key is not None or bool(pilot_skus_raw) or pilot_reference is not None
    remote_requested = (
        settings.agent_payment_gateway_url is not None
        or settings.agent_payment_gateway_protocol is not None
    )

    if pilot_requested and remote_requested:
        raise ValueError(
            "founding pilot access and remote payment gateway configuration are mutually exclusive"
        )
    if not pilot_requested:
        return build_configured_payment_gateway(settings)
    if pilot_key is None:
        raise ValueError("OILSIGNAL_AGENT_PILOT_ACCESS_KEY is required for founding pilot access")
    if not pilot_skus_raw:
        raise ValueError("OILSIGNAL_AGENT_PILOT_SKUS must list at least one product")

    skus = [item.strip() for item in pilot_skus_raw.split(",") if item.strip()]
    if len(set(skus)) != len(skus):
        raise ValueError("OILSIGNAL_AGENT_PILOT_SKUS must not contain duplicate SKUs")
    unknown = sorted(sku for sku in skus if not product_exists(sku))
    if unknown:
        raise ValueError("unknown founding pilot SKUs: " + ", ".join(unknown))

    reference = pilot_reference.strip() if pilot_reference is not None else None
    return PilotAccessGateway(
        pilot_key.get_secret_value(),
        customer=settings.agent_pilot_customer,
        allowed_skus=frozenset(skus),
        reference=reference,
    )
