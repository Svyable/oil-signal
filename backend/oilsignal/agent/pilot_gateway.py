from __future__ import annotations

import hmac
from collections.abc import Mapping

from oilsignal.agent.commerce import (
    PaymentChallenge,
    PaymentRejected,
    PaymentRequirement,
    VerifiedPayment,
)

PILOT_PROTOCOL = "oilsignal-pilot-v1"
PILOT_CREDENTIAL_HEADER = "X-OilSignal-Pilot-Key"
_MIN_ACCESS_KEY_LENGTH = 24
_MAX_ACCESS_KEY_LENGTH = 4096


class PilotAccessGateway:
    """Scoped first-customer access without pretending to settle money.

    This adapter is for a manually invoiced or explicitly granted founding pilot.
    It reuses OilSignal's evidence-bound HTTP 402 fulfillment path so the same
    price, receipt-binding, and fulfillment-audit invariants apply, while the
    commercial agreement itself remains outside OilSignal.
    """

    protocol = PILOT_PROTOCOL
    credential_headers = (PILOT_CREDENTIAL_HEADER,)

    def __init__(
        self,
        access_key: str,
        *,
        customer: str,
        allowed_skus: frozenset[str],
        reference: str | None = None,
    ) -> None:
        if len(access_key) < _MIN_ACCESS_KEY_LENGTH:
            raise ValueError(
                f"pilot access key must be at least {_MIN_ACCESS_KEY_LENGTH} characters"
            )
        if len(access_key) > _MAX_ACCESS_KEY_LENGTH:
            raise ValueError("pilot access key is too long")
        normalized_customer = customer.strip()
        if not normalized_customer:
            raise ValueError("pilot customer label must not be empty")
        if not allowed_skus:
            raise ValueError("pilot access must allow at least one SKU")
        normalized_reference = reference.strip() if reference is not None else None
        if normalized_reference == "":
            normalized_reference = None

        self._access_key = access_key
        self.customer = normalized_customer
        self.allowed_skus = allowed_skus
        self.reference = normalized_reference or f"pilot:{normalized_customer}"

    def challenge(self, requirement: PaymentRequirement) -> PaymentChallenge:
        return PaymentChallenge(
            protocol=self.protocol,
            challenge_id=f"pilot:{requirement.sku}",
            response_headers={
                "WWW-Authenticate": 'OilSignalPilot realm="OilSignal"',
                "X-OilSignal-Pilot-Required": PILOT_CREDENTIAL_HEADER,
            },
        )

    def verify(
        self,
        request_headers: Mapping[str, str],
        requirement: PaymentRequirement,
    ) -> VerifiedPayment:
        if requirement.sku not in self.allowed_skus:
            raise PaymentRejected("pilot access is not enabled for this product")

        incoming = {key.lower(): value for key, value in request_headers.items()}
        provided = incoming.get(PILOT_CREDENTIAL_HEADER.lower())
        if (
            not provided
            or len(provided) > _MAX_ACCESS_KEY_LENGTH
            or not hmac.compare_digest(provided, self._access_key)
        ):
            raise PaymentRejected("pilot access key was rejected")

        return VerifiedPayment(
            protocol=self.protocol,
            response_headers={"X-OilSignal-Pilot-Access": "granted"},
            external_id=requirement.external_id,
            reference=self.reference,
            payer=f"pilot:{self.customer}",
        )
