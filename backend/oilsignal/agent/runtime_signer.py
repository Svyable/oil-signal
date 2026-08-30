from __future__ import annotations

from oilsignal.agent.signatures import EvidenceSigner
from oilsignal.config import Settings


def build_runtime_evidence_signer(settings: Settings) -> EvidenceSigner | None:
    private_key = settings.agent_evidence_signing_private_key
    if private_key is None:
        if settings.agent_evidence_signing_key_id is not None:
            raise ValueError(
                "OILSIGNAL_AGENT_EVIDENCE_SIGNING_PRIVATE_KEY is required when a signing key ID is configured"
            )
        return None
    return EvidenceSigner.from_private_key_b64(
        private_key.get_secret_value(),
        key_id=settings.agent_evidence_signing_key_id,
    )
