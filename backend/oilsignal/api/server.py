from oilsignal.agent.http_payment_gateway import build_configured_payment_gateway
from oilsignal.api.app import create_app
from oilsignal.config import settings

app = create_app(payment_gateway=build_configured_payment_gateway(settings))
