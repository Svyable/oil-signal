from decimal import Decimal

import httpx
import pytest
from oilsignal.agent.commerce import (
    PaymentGatewayUnavailable,
    PaymentRejected,
    build_payment_requirement,
)
from oilsignal.agent.http_payment_gateway import HttpPaymentGateway


def _requirement():
    return build_payment_requirement(
        sku="weekly-petroleum-evidence",
        amount=Decimal("0.05"),
        currency="USD",
        evidence_sha256="b" * 64,
        description="Weekly Petroleum Brief",
    )


def test_empty_remote_external_id_is_invalid_receipt() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "protocol": "mpp",
                "external_id": "",
                "reference": "settlement-1",
                "payer": None,
                "response_headers": {"Payment-Receipt": "receipt-token"},
            },
        )

    gateway = HttpPaymentGateway(
        "http://payments.local",
        protocol="mpp",
        credential_headers=("Authorization",),
        allow_insecure_http=True,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(PaymentGatewayUnavailable, match="invalid receipt"):
        gateway.verify({"Authorization": "Payment paid"}, _requirement())


def test_oversized_buyer_credential_is_rejected_without_remote_call() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    gateway = HttpPaymentGateway(
        "http://payments.local",
        protocol="mpp",
        credential_headers=("Authorization",),
        allow_insecure_http=True,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(PaymentRejected, match="payment credential was rejected"):
        gateway.verify({"Authorization": "x" * 16385}, _requirement())

    assert calls == 0
