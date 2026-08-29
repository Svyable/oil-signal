import json
from decimal import Decimal

import httpx
import pytest
from oilsignal.agent.commerce import (
    PaymentGatewayUnavailable,
    PaymentRejected,
    PaymentRequirement,
    build_payment_requirement,
)
from oilsignal.agent.http_payment_gateway import (
    GATEWAY_CONTRACT_VERSION,
    HttpPaymentGateway,
    build_configured_payment_gateway,
)
from oilsignal.config import Settings


def _requirement() -> PaymentRequirement:
    return build_payment_requirement(
        sku="weekly-petroleum-evidence",
        amount=Decimal("0.05"),
        currency="USD",
        evidence_sha256="a" * 64,
        description="Weekly Petroleum Brief",
    )


def test_challenge_posts_only_evidence_bound_contract() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        seen["contract"] = request.headers.get("x-oilsignal-gateway-contract")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "protocol": "mpp",
                "challenge_id": "challenge-1",
                "response_headers": {"WWW-Authenticate": "Payment challenge-token"},
            },
        )

    gateway = HttpPaymentGateway(
        "http://payments.local/oilsignal",
        protocol="mpp",
        credential_headers=("Authorization",),
        bearer_token="operator-secret",
        allow_insecure_http=True,
        transport=httpx.MockTransport(handler),
    )

    challenge = gateway.challenge(_requirement())

    assert seen["url"] == "http://payments.local/oilsignal/challenge"
    assert seen["authorization"] == "Bearer operator-secret"
    assert seen["contract"] == GATEWAY_CONTRACT_VERSION
    payload = seen["payload"]
    assert isinstance(payload, dict)
    assert payload["contract_version"] == GATEWAY_CONTRACT_VERSION
    assert payload["requirement"]["external_id"].endswith("a" * 64)
    assert payload["requirement"]["amount"] == "0.05"
    assert challenge.challenge_id == "challenge-1"
    assert challenge.response_headers["WWW-Authenticate"] == "Payment challenge-token"


def test_verify_forwards_only_declared_payment_credentials() -> None:
    seen: dict[str, object] = {}
    requirement = _requirement()

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "protocol": "x402-v2",
                "external_id": requirement.external_id,
                "reference": "settlement-1",
                "payer": "buyer-1",
                "response_headers": {"PAYMENT-RESPONSE": "settled-token"},
            },
        )

    gateway = HttpPaymentGateway(
        "http://payments.local",
        protocol="x402-v2",
        credential_headers=("PAYMENT-SIGNATURE",),
        bearer_token="operator-secret",
        allow_insecure_http=True,
        transport=httpx.MockTransport(handler),
    )

    verified = gateway.verify(
        {
            "PAYMENT-SIGNATURE": "buyer-signature",
            "Cookie": "session=must-not-leave-process",
            "X-Unrelated": "must-not-leave-process",
            "Authorization": "Bearer unrelated-client-token",
        },
        requirement,
    )

    assert seen["authorization"] == "Bearer operator-secret"
    payload = seen["payload"]
    assert isinstance(payload, dict)
    assert payload["credentials"] == {"PAYMENT-SIGNATURE": "buyer-signature"}
    serialized = json.dumps(payload)
    assert "session=must-not-leave-process" not in serialized
    assert "unrelated-client-token" not in serialized
    assert verified.external_id == requirement.external_id
    assert verified.reference == "settlement-1"
    assert verified.response_headers == {"PAYMENT-RESPONSE": "settled-token"}


def test_missing_declared_credential_rejects_without_remote_call() -> None:
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

    with pytest.raises(PaymentRejected, match="payment credential is required"):
        gateway.verify({"X-Unrelated": "value"}, _requirement())

    assert calls == 0


def test_remote_402_is_sanitized_buyer_rejection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"detail": "provider-secret-should-not-leak"})

    gateway = HttpPaymentGateway(
        "http://payments.local",
        protocol="mpp",
        credential_headers=("Authorization",),
        allow_insecure_http=True,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(PaymentRejected) as exc_info:
        gateway.verify({"Authorization": "Payment bad"}, _requirement())

    assert str(exc_info.value) == "payment credential was rejected"
    assert "provider-secret" not in str(exc_info.value)


def test_remote_failure_and_transport_errors_are_sanitized() -> None:
    def failed_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="database password=do-not-leak")

    failed_gateway = HttpPaymentGateway(
        "http://payments.local",
        protocol="mpp",
        credential_headers=("Authorization",),
        allow_insecure_http=True,
        transport=httpx.MockTransport(failed_handler),
    )
    with pytest.raises(PaymentGatewayUnavailable) as exc_info:
        failed_gateway.challenge(_requirement())
    assert str(exc_info.value) == "payment gateway challenge returned HTTP 500"
    assert "password" not in str(exc_info.value)

    def broken_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret endpoint detail", request=request)

    broken_gateway = HttpPaymentGateway(
        "http://payments.local",
        protocol="mpp",
        credential_headers=("Authorization",),
        allow_insecure_http=True,
        transport=httpx.MockTransport(broken_handler),
    )
    with pytest.raises(PaymentGatewayUnavailable) as transport_exc:
        broken_gateway.challenge(_requirement())
    assert str(transport_exc.value) == "payment gateway transport failed: ConnectError"
    assert "secret endpoint detail" not in str(transport_exc.value)


def test_gateway_rejects_redirects_as_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(307, headers={"Location": "http://other.local/challenge"})

    gateway = HttpPaymentGateway(
        "http://payments.local",
        protocol="mpp",
        credential_headers=("Authorization",),
        allow_insecure_http=True,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(PaymentGatewayUnavailable, match="HTTP 307"):
        gateway.challenge(_requirement())


def test_gateway_validates_url_and_credential_header_configuration() -> None:
    with pytest.raises(ValueError, match="must use https"):
        HttpPaymentGateway(
            "http://payments.example.com",
            protocol="mpp",
            credential_headers=("Authorization",),
        )
    with pytest.raises(ValueError, match="embedded credentials"):
        HttpPaymentGateway(
            "https://user:pass@payments.example.com",
            protocol="mpp",
            credential_headers=("Authorization",),
        )
    with pytest.raises(ValueError, match="query string or fragment"):
        HttpPaymentGateway(
            "https://payments.example.com?token=bad-place-for-secret",
            protocol="mpp",
            credential_headers=("Authorization",),
        )
    with pytest.raises(ValueError, match="not allowed"):
        HttpPaymentGateway(
            "https://payments.example.com",
            protocol="mpp",
            credential_headers=("Cookie",),
        )
    with pytest.raises(ValueError, match="duplicate"):
        HttpPaymentGateway(
            "https://payments.example.com",
            protocol="mpp",
            credential_headers=("Authorization", "authorization"),
        )


def test_gateway_rejects_malformed_remote_headers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "protocol": "mpp",
                "challenge_id": "challenge-1",
                "response_headers": {"WWW-Authenticate": "Payment good\r\nX-Evil: yes"},
            },
        )

    gateway = HttpPaymentGateway(
        "http://payments.local",
        protocol="mpp",
        credential_headers=("Authorization",),
        allow_insecure_http=True,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(PaymentGatewayUnavailable, match="invalid response header"):
        gateway.challenge(_requirement())


def test_settings_factory_is_off_by_default_and_fails_fast_on_partial_config() -> None:
    assert build_configured_payment_gateway(Settings()) is None

    with pytest.raises(ValueError, match="must be configured together"):
        build_configured_payment_gateway(
            Settings(agent_payment_gateway_url="https://payments.example.com")
        )

    gateway = build_configured_payment_gateway(
        Settings(
            agent_payment_gateway_url="https://payments.example.com/oilsignal",
            agent_payment_gateway_protocol="x402-v2",
            agent_payment_gateway_credential_headers="PAYMENT-SIGNATURE, X-PAYMENT-NONCE",
            agent_payment_gateway_bearer_token="operator-secret",
        )
    )

    assert isinstance(gateway, HttpPaymentGateway)
    assert gateway.protocol == "x402-v2"
    assert gateway.credential_headers == ("PAYMENT-SIGNATURE", "X-PAYMENT-NONCE")
    assert gateway.bearer_token == "operator-secret"


def test_empty_optional_environment_values_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OILSIGNAL_AGENT_EVIDENCE_PACK_PRICE_USD", "")
    monkeypatch.setenv("OILSIGNAL_AGENT_PAYMENT_GATEWAY_URL", "")
    monkeypatch.setenv("OILSIGNAL_AGENT_PAYMENT_GATEWAY_TIMEOUT_SECONDS", "")

    configured = Settings(_env_file=None)

    assert configured.agent_evidence_pack_price_usd is None
    assert configured.agent_payment_gateway_url is None
    assert configured.agent_payment_gateway_timeout_seconds == 5.0
