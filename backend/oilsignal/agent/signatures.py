from __future__ import annotations

import base64
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest

from pydantic import BaseModel, Field

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
except ImportError:  # pragma: no cover - optional runtime capability
    InvalidSignature = Exception  # type: ignore[assignment,misc]
    serialization = None  # type: ignore[assignment]
    Ed25519PrivateKey = None  # type: ignore[assignment,misc]
    Ed25519PublicKey = None  # type: ignore[assignment,misc]

SIGNATURE_SCHEMA_VERSION = "1.0"
SIGNATURE_ALGORITHM = "Ed25519"
SIGNATURE_CONTEXT = "oilsignal-evidence-v1"


class EvidenceSignature(BaseModel):
    schema_version: str = SIGNATURE_SCHEMA_VERSION
    algorithm: str = SIGNATURE_ALGORITHM
    key_id: str
    context: str = SIGNATURE_CONTEXT
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature: str


class EvidenceVerificationKey(BaseModel):
    schema_version: str = SIGNATURE_SCHEMA_VERSION
    algorithm: str = SIGNATURE_ALGORITHM
    key_id: str
    public_key: str


@dataclass(frozen=True)
class EvidenceSigner:
    key_id: str
    private_key: object
    public_key_bytes: bytes

    @classmethod
    def from_private_key_b64(cls, private_key_b64: str, *, key_id: str | None = None) -> EvidenceSigner:
        if Ed25519PrivateKey is None or serialization is None:
            raise RuntimeError("evidence signing requires the 'crypto' optional dependency")
        try:
            raw = base64.b64decode(private_key_b64, validate=True)
            private_key = Ed25519PrivateKey.from_private_bytes(raw)
        except (ValueError, TypeError) as exc:
            raise ValueError("evidence signing key must be base64-encoded 32-byte Ed25519 private key") from exc
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        resolved_key_id = key_id or f"ed25519:{sha256(public_key).hexdigest()[:16]}"
        return cls(key_id=resolved_key_id, private_key=private_key, public_key_bytes=public_key)

    def verification_key(self) -> EvidenceVerificationKey:
        return EvidenceVerificationKey(
            key_id=self.key_id,
            public_key=base64.b64encode(self.public_key_bytes).decode("ascii"),
        )

    def sign(self, evidence_sha256: str) -> EvidenceSignature:
        message = signature_message(evidence_sha256)
        signature = self.private_key.sign(message)  # type: ignore[attr-defined]
        return EvidenceSignature(
            key_id=self.key_id,
            evidence_sha256=evidence_sha256,
            signature=base64.b64encode(signature).decode("ascii"),
        )


def signature_message(evidence_sha256: str) -> bytes:
    if len(evidence_sha256) != 64 or any(char not in "0123456789abcdef" for char in evidence_sha256):
        raise ValueError("evidence digest must be lowercase hexadecimal SHA-256")
    return f"{SIGNATURE_CONTEXT}\nsha256:{evidence_sha256}\n".encode()


def verify_evidence_signature(signature: EvidenceSignature, key: EvidenceVerificationKey) -> bool:
    if signature.algorithm != SIGNATURE_ALGORITHM or key.algorithm != SIGNATURE_ALGORITHM:
        return False
    if not compare_digest(signature.key_id, key.key_id):
        return False
    if Ed25519PublicKey is None:
        raise RuntimeError("evidence signature verification requires the 'crypto' optional dependency")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(key.public_key, validate=True))
        signature_bytes = base64.b64decode(signature.signature, validate=True)
        public_key.verify(signature_bytes, signature_message(signature.evidence_sha256))
    except (ValueError, TypeError, InvalidSignature):
        return False
    return True
