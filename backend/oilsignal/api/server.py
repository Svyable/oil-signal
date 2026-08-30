from oilsignal.agent.runtime_gateway import build_runtime_payment_gateway
from oilsignal.agent.runtime_signer import build_runtime_evidence_signer
from oilsignal.api.app import create_app
from oilsignal.config import settings

app = create_app(
    payment_gateway=build_runtime_payment_gateway(settings),
    evidence_signer=build_runtime_evidence_signer(settings),
)
