from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field


class PaymentRequirement(BaseModel):
    """The immutable commercial facts a payment must authorize."""

    sku: str
    amount: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    resource_path: str
    evidence_sha256: str = Field(min_length=64, max_length=64)
    external_id: str
    description: str


class PaymentChallenge(BaseModel):
    """Wire challenge returned by a payment adapter for HTTP 402."""

    protocol: str
    www_authenticate: str = Field(min_length=1)
    challenge_id: str | None = None


class VerifiedPayment(BaseModel):
    """Successful adapter verification, including its standard receipt header."""

    protocol: str
    receipt_header: str = Field(min_length=1)
    reference: str | None = None
    payer: str | None = None


class PaymentProblem(BaseModel):
    """Machine-readable 402 body that never contains the purchased evidence."""

    type: str = "urn:oilsignal:payment-required"
    title: str = "Payment Required"
    status: int = 402
    detail: str
    sku: str
    amount: Decimal
    currency: str
    evidence_sha256: str
    external_id: str
    payment_protocol: str


class PaymentGatewayError(RuntimeError):
    """Base class for gateway failures safe to map at the HTTP boundary."""


class PaymentRejected(PaymentGatewayError):
    """The supplied payment credential did not authorize this requirement."""

    def __init__(self, detail: str = "payment credential was rejected") -> None:
        super().__init__(detail)
        self.detail = detail


class PaymentGatewayUnavailable(PaymentGatewayError):
    """The configured payment adapter could not challenge or verify payment."""


class PaymentGateway(Protocol):
    """Payment-method agnostic HTTP 402 adapter boundary.

    Implementations can speak MPP, x402, credits, cards, stablecoins, or another
    rail. The core passes the exact evidence-bound requirement into both challenge
    generation and verification; adapters are responsible for settlement,
    credential replay protection, and provider-specific receipt semantics.
    """

    protocol: str

    def challenge(self, requirement: PaymentRequirement) -> PaymentChallenge: ...

    def verify(
        self,
        authorization: str,
        requirement: PaymentRequirement,
    ) -> VerifiedPayment: ...


def build_payment_requirement(
    *,
    sku: str,
    amount: Decimal,
    currency: str,
    evidence_sha256: str,
    description: str,
) -> PaymentRequirement:
    resource_path = f"/api/agent/products/{sku}/evidence"
    external_id = f"oilsignal:{sku}:sha256:{evidence_sha256}"
    return PaymentRequirement(
        sku=sku,
        amount=amount,
        currency=currency.upper(),
        resource_path=resource_path,
        evidence_sha256=evidence_sha256,
        external_id=external_id,
        description=description,
    )
