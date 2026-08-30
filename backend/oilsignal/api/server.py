from oilsignal.agent.runtime_gateway import build_runtime_payment_gateway
from oilsignal.api.app import create_app
from oilsignal.config import settings

app = create_app(payment_gateway=build_runtime_payment_gateway(settings))
