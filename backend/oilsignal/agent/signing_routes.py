from __future__ import annotations

from fastapi import FastAPI, HTTPException

from oilsignal.agent.products import build_evidence_pack, product_exists
from oilsignal.agent.signatures import EvidenceSignature, EvidenceSigner, EvidenceVerificationKey
from oilsignal.freshness import require_fresh_wpsr
from oilsignal.storage.datasets import inspect_data, load_latest_observations


def attach_evidence_signing_routes(app: FastAPI, signer: EvidenceSigner | None) -> None:
    """Attach optional detached-signature routes without changing evidence identity."""

    app.state.evidence_signer = signer

    @app.get("/.well-known/oilsignal-evidence-key.json", response_model=EvidenceVerificationKey)
    def evidence_verification_key() -> EvidenceVerificationKey:
        if signer is None:
            raise HTTPException(status_code=404, detail="evidence signing is not configured")
        return signer.verification_key()

    @app.get(
        "/api/agent/products/{sku}/signature",
        response_model=EvidenceSignature,
        responses={
            404: {"description": "Unknown product or evidence signing is not configured"},
            409: {"description": "Evidence cannot be built from the current dataset"},
        },
    )
    def evidence_signature(sku: str) -> EvidenceSignature:
        if signer is None:
            raise HTTPException(status_code=404, detail="evidence signing is not configured")
        if not product_exists(sku):
            raise HTTPException(status_code=404, detail=f"unknown agent product: {sku}")
        try:
            data_status = inspect_data(app.state.data_dir)
            observations = load_latest_observations(app.state.data_dir)
            freshness = require_fresh_wpsr(observations, live_eia=data_status.is_live_eia)
            pack = build_evidence_pack(
                sku,
                observations,
                freshness=freshness,
                data_source=data_status.source,
                source_fetched_at=data_status.latest_fetched_at,
            )
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return signer.sign(pack.evidence_sha256)
