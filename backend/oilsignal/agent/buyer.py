from __future__ import annotations

from collections.abc import Mapping

import httpx
from pydantic import BaseModel

from oilsignal.agent.commerce import PaymentProblem
from oilsignal.agent.manifest import AgentChangeManifest
from oilsignal.agent.products import AgentCatalog, AgentQuote, EvidencePack
from oilsignal.agent.state import AgentProductState


class BuyerClientError(RuntimeError):
    """Base error raised by the machine buyer helper."""


class BuyerIntegrityError(BuyerClientError):
    """Returned evidence/state identity did not match OilSignal response headers."""


class BuyerPaymentRequired(BuyerClientError):
    """The seller returned an evidence-bound HTTP 402 challenge."""

    def __init__(self, problem: PaymentProblem, headers: Mapping[str, str]) -> None:
        super().__init__(problem.detail)
        self.problem = problem
        self.headers = dict(headers)


class ManifestPoll(BaseModel):
    not_modified: bool
    etag: str | None = None
    manifest: AgentChangeManifest | None = None


class StatePoll(BaseModel):
    not_modified: bool
    etag: str | None = None
    state: AgentProductState | None = None


class EvidenceFetch(BaseModel):
    not_modified: bool
    etag: str | None = None
    evidence: EvidencePack | None = None


class OilSignalBuyer:
    """Small synchronous client for OilSignal's machine-product lifecycle."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        normalized = base_url.rstrip("/")
        if not normalized:
            raise ValueError("buyer base URL must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("buyer timeout must be positive")
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=normalized, timeout=timeout_seconds)

    def __enter__(self) -> OilSignalBuyer:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def catalog(self) -> AgentCatalog:
        response = self._client.get("/.well-known/oilsignal-agent.json")
        response.raise_for_status()
        return AgentCatalog.model_validate(response.json())

    def quote(self, sku: str) -> AgentQuote:
        response = self._client.get(f"/api/agent/products/{sku}/quote")
        response.raise_for_status()
        return AgentQuote.model_validate(response.json())

    def poll_manifest(self, *, etag: str | None = None) -> ManifestPoll:
        headers = {"If-None-Match": etag} if etag else None
        response = self._client.get("/api/agent/manifest", headers=headers)
        if response.status_code == 304:
            return ManifestPoll(not_modified=True, etag=response.headers.get("etag"))
        response.raise_for_status()
        manifest = AgentChangeManifest.model_validate(response.json())
        _require_header_identity(
            response,
            "x-oilsignal-manifest-sha256",
            manifest.manifest_sha256,
            label="catalog manifest",
        )
        expected_etag = f'W/"sha256:{manifest.manifest_sha256}"'
        returned_etag = response.headers.get("etag")
        if returned_etag != expected_etag:
            raise BuyerIntegrityError("catalog manifest ETag does not match manifest digest")
        return ManifestPoll(
            not_modified=False,
            etag=returned_etag,
            manifest=manifest,
        )

    def poll_state(self, sku: str, *, etag: str | None = None) -> StatePoll:
        headers = {"If-None-Match": etag} if etag else None
        response = self._client.get(f"/api/agent/products/{sku}/state", headers=headers)
        if response.status_code == 304:
            return StatePoll(not_modified=True, etag=response.headers.get("etag"))
        response.raise_for_status()
        state = AgentProductState.model_validate(response.json())
        _require_header_identity(
            response,
            "x-oilsignal-state-sha256",
            state.state_sha256,
            label="product state",
        )
        _require_header_identity(
            response,
            "x-oilsignal-evidence-sha256",
            state.evidence_sha256,
            label="state evidence",
        )
        return StatePoll(
            not_modified=False,
            etag=response.headers.get("etag"),
            state=state,
        )

    def fetch_evidence(
        self,
        sku: str,
        *,
        credential_headers: Mapping[str, str] | None = None,
        etag: str | None = None,
        expected_evidence_sha256: str | None = None,
    ) -> EvidenceFetch:
        headers = dict(credential_headers or {})
        if etag:
            headers["If-None-Match"] = etag
        response = self._client.get(
            f"/api/agent/products/{sku}/evidence",
            headers=headers or None,
        )
        if response.status_code == 304:
            return EvidenceFetch(not_modified=True, etag=response.headers.get("etag"))
        if response.status_code == 402:
            problem = PaymentProblem.model_validate(response.json())
            _require_header_identity(
                response,
                "x-oilsignal-evidence-sha256",
                problem.evidence_sha256,
                label="payment challenge evidence",
            )
            raise BuyerPaymentRequired(problem, response.headers)
        response.raise_for_status()
        evidence = EvidencePack.model_validate(response.json())
        _require_header_identity(
            response,
            "x-oilsignal-evidence-sha256",
            evidence.evidence_sha256,
            label="evidence",
        )
        if expected_evidence_sha256 and evidence.evidence_sha256 != expected_evidence_sha256:
            raise BuyerIntegrityError(
                "fulfilled evidence digest does not match the digest observed in product state"
            )
        expected_etag = f'W/"sha256:{evidence.evidence_sha256}"'
        returned_etag = response.headers.get("etag")
        if returned_etag != expected_etag:
            raise BuyerIntegrityError("evidence ETag does not match the fulfilled evidence digest")
        return EvidenceFetch(
            not_modified=False,
            etag=returned_etag,
            evidence=evidence,
        )


def _require_header_identity(
    response: httpx.Response,
    header: str,
    expected: str,
    *,
    label: str,
) -> None:
    value = response.headers.get(header)
    if value != expected:
        raise BuyerIntegrityError(f"{label} digest does not match response header {header}")
