from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from oilsignal.agent.signatures import EvidenceSignature, EvidenceSigner, verify_evidence_signature
from oilsignal.agent.signing_routes import attach_evidence_signing_routes
from oilsignal.api.app import create_app


def _signer() -> EvidenceSigner:
    raw = Ed25519PrivateKey.generate().private_bytes_raw()
    return EvidenceSigner.from_private_key_b64(base64.b64encode(raw).decode("ascii"), key_id="test-key")


def test_signer_verifies_and_rejects_tampered_digest() -> None:
    signer = _signer()
    digest = "a" * 64
    signature = signer.sign(digest)

    assert verify_evidence_signature(signature, signer.verification_key())
    tampered = signature.model_copy(update={"evidence_sha256": "b" * 64})
    assert not verify_evidence_signature(tampered, signer.verification_key())


def test_signing_routes_bind_signature_to_current_evidence(fixture_data_dir) -> None:
    signer = _signer()
    app = create_app(data_dir=fixture_data_dir)
    attach_evidence_signing_routes(app, signer)
    client = TestClient(app)

    evidence = client.get("/api/agent/products/fact-us-crude-stocks/evidence")
    assert evidence.status_code == 200
    signature_response = client.get("/api/agent/products/fact-us-crude-stocks/signature")
    assert signature_response.status_code == 200
    signature = EvidenceSignature.model_validate(signature_response.json())

    assert signature.evidence_sha256 == evidence.json()["evidence_sha256"]
    assert verify_evidence_signature(signature, signer.verification_key())
    key_response = client.get("/.well-known/oilsignal-evidence-key.json")
    assert key_response.status_code == 200
    assert key_response.json()["key_id"] == "test-key"


def test_signing_routes_are_absent_when_operator_does_not_configure_key(fixture_data_dir) -> None:
    app = create_app(data_dir=fixture_data_dir)
    attach_evidence_signing_routes(app, None)
    client = TestClient(app)

    assert client.get("/.well-known/oilsignal-evidence-key.json").status_code == 404
    assert client.get("/api/agent/products/fact-us-crude-stocks/signature").status_code == 404
