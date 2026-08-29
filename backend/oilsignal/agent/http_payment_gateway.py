from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from oilsignal.agent.commerce import (
    PaymentChallenge,
    PaymentGateway,
    PaymentGatewayUnavailable,
    PaymentRejected,
    PaymentRequirement,
    VerifiedPayment,
)
from oilsignal.config import Settings

GATEWAY_CONTRACT_VERSION = "oilsignal.payment-gateway.v1"
_HTTP_TOKEN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_FORBIDDEN_CREDENTIAL_HEADERS = {
    "connection",
    "content-length",
    "content-type",
    "cookie",
    "host",
    "origin",
    "referer",
    "transfer-encoding",
    "user-agent",
}
_MAX_CREDENTIAL_VALUE_LENGTH = 16384
_MAX_RESPONSE_HEADERS = 32
_MAX_HEADER_VALUE_LENGTH = 8192


class _ChallengeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol: str = Field(min_length=1, max_length=128)
    response_headers: dict[str, str]
    challenge_id: str | None = Field(default=None, max_length=512)


class _VerifyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol: str = Field(min_length=1, max_length=128)
    response_headers: dict[str, str]
    external_id: str = Field(min_length=1, max_length=1024)
    reference: str | None = Field(default=None, max_length=512)
    payer: str | None = Field(default=None, max_length=512)


class HttpPaymentGateway:
    """Remote bridge for a real payment verifier/settlement service.

    The remote service owns payment-protocol specifics. OilSignal sends only the
    immutable evidence-bound requirement and explicitly configured credential
    headers. No arbitrary browser/request headers are forwarded.
    """

    def __init__(
        self,
        base_url: str,
        *,
        protocol: str,
        credential_headers: tuple[str, ...],
        bearer_token: str | None = None,
        timeout_seconds: float = 5.0,
        allow_insecure_http: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("payment gateway URL must be an absolute http(s) URL")
        if parsed.username or parsed.password:
            raise ValueError("payment gateway URL must not contain embedded credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("payment gateway URL must not contain a query string or fragment")
        if parsed.scheme == "http" and not allow_insecure_http:
            raise ValueError(
                "payment gateway URL must use https unless insecure HTTP is explicitly enabled"
            )
        if timeout_seconds <= 0:
            raise ValueError("payment gateway timeout_seconds must be positive")
        if not protocol.strip():
            raise ValueError("payment gateway protocol must not be empty")

        normalized_headers = _validate_credential_headers(credential_headers)
        self.base_url = base_url.rstrip("/")
        self.protocol = protocol.strip()
        self.credential_headers = normalized_headers
        self.bearer_token = bearer_token
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def challenge(self, requirement: PaymentRequirement) -> PaymentChallenge:
        response = self._post(
            "/challenge",
            {
                "contract_version": GATEWAY_CONTRACT_VERSION,
                "requirement": requirement.model_dump(mode="json"),
            },
        )
        if not 200 <= response.status_code < 300:
            raise PaymentGatewayUnavailable(
                f"payment gateway challenge returned HTTP {response.status_code}"
            )
        try:
            payload = _ChallengeResponse.model_validate(response.json())
        except (ValueError, ValidationError):
            raise PaymentGatewayUnavailable("payment gateway returned an invalid challenge") from None
        response_headers = _validate_response_headers(payload.response_headers)
        return PaymentChallenge(
            protocol=payload.protocol,
            response_headers=response_headers,
            challenge_id=payload.challenge_id,
        )

    def verify(
        self,
        request_headers: Mapping[str, str],
        requirement: PaymentRequirement,
    ) -> VerifiedPayment:
        credentials = _select_credentials(request_headers, self.credential_headers)
        if not credentials:
            raise PaymentRejected("payment credential is required")

        response = self._post(
            "/verify",
            {
                "contract_version": GATEWAY_CONTRACT_VERSION,
                "requirement": requirement.model_dump(mode="json"),
                "credentials": credentials,
            },
        )
        if response.status_code == 402:
            raise PaymentRejected("payment credential was rejected")
        if not 200 <= response.status_code < 300:
            raise PaymentGatewayUnavailable(
                f"payment gateway verification returned HTTP {response.status_code}"
            )
        try:
            payload = _VerifyResponse.model_validate(response.json())
        except (ValueError, ValidationError):
            raise PaymentGatewayUnavailable("payment gateway returned an invalid receipt") from None
        response_headers = _validate_response_headers(payload.response_headers)
        return VerifiedPayment(
            protocol=payload.protocol,
            response_headers=response_headers,
            external_id=payload.external_id,
            reference=payload.reference,
            payer=payload.payer,
        )

    def _post(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "OilSignal/0.2",
            "X-OilSignal-Gateway-Contract": GATEWAY_CONTRACT_VERSION,
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                return client.post(f"{self.base_url}{path}", json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise PaymentGatewayUnavailable(
                f"payment gateway transport failed: {exc.__class__.__name__}"
            ) from None


def build_configured_payment_gateway(settings: Settings) -> PaymentGateway | None:
    """Build the module-level payment bridge only when operator config is complete."""

    url = settings.agent_payment_gateway_url
    protocol = settings.agent_payment_gateway_protocol
    if url is None and protocol is None:
        return None
    if not url or not protocol:
        raise ValueError(
            "OILSIGNAL_AGENT_PAYMENT_GATEWAY_URL and "
            "OILSIGNAL_AGENT_PAYMENT_GATEWAY_PROTOCOL must be configured together"
        )
    credential_headers = tuple(
        item.strip()
        for item in settings.agent_payment_gateway_credential_headers.split(",")
        if item.strip()
    )
    token = (
        settings.agent_payment_gateway_bearer_token.get_secret_value()
        if settings.agent_payment_gateway_bearer_token
        else None
    )
    return HttpPaymentGateway(
        url,
        protocol=protocol,
        credential_headers=credential_headers,
        bearer_token=token,
        timeout_seconds=settings.agent_payment_gateway_timeout_seconds,
        allow_insecure_http=settings.agent_payment_gateway_allow_insecure_http,
    )


def _validate_credential_headers(headers: tuple[str, ...]) -> tuple[str, ...]:
    if not headers:
        raise ValueError("payment gateway must declare at least one credential header")
    if len(headers) > 8:
        raise ValueError("payment gateway supports at most 8 credential headers")

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_name in headers:
        name = raw_name.strip()
        lowered = name.lower()
        if not name or not _HTTP_TOKEN.fullmatch(name):
            raise ValueError(f"invalid payment credential header name: {raw_name!r}")
        if lowered in _FORBIDDEN_CREDENTIAL_HEADERS:
            raise ValueError(f"payment credential header is not allowed: {name}")
        if lowered in seen:
            raise ValueError(f"duplicate payment credential header: {name}")
        seen.add(lowered)
        normalized.append(name)
    return tuple(normalized)


def _select_credentials(
    request_headers: Mapping[str, str],
    credential_headers: tuple[str, ...],
) -> dict[str, str]:
    incoming = {key.lower(): value for key, value in request_headers.items()}
    selected: dict[str, str] = {}
    for header_name in credential_headers:
        value = incoming.get(header_name.lower())
        if not value:
            continue
        if len(value) > _MAX_CREDENTIAL_VALUE_LENGTH:
            raise PaymentRejected("payment credential was rejected")
        selected[header_name] = value
    return selected


def _validate_response_headers(headers: dict[str, str]) -> dict[str, str]:
    if len(headers) > _MAX_RESPONSE_HEADERS:
        raise PaymentGatewayUnavailable("payment gateway returned too many response headers")
    validated: dict[str, str] = {}
    for name, value in headers.items():
        if not _HTTP_TOKEN.fullmatch(name):
            raise PaymentGatewayUnavailable("payment gateway returned an invalid response header")
        if "\r" in value or "\n" in value or len(value) > _MAX_HEADER_VALUE_LENGTH:
            raise PaymentGatewayUnavailable("payment gateway returned an invalid response header")
        validated[name] = value
    return validated
