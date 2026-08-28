from decimal import Decimal
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with safe local defaults."""

    model_config = SettingsConfigDict(env_prefix="OILSIGNAL_", env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")
    eia_api_key: str | None = None
    eia_base_url: str = "https://api.eia.gov/v2"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    alert_webhook_url: str | None = None
    alert_webhook_bearer_token: SecretStr | None = None
    alert_webhook_signing_secret: SecretStr | None = None
    alert_webhook_timeout_seconds: float = Field(default=10.0, gt=0)
    alert_webhook_allow_insecure_http: bool = False
    agent_evidence_pack_price_usd: Decimal | None = Field(default=None, ge=0)
    agent_price_currency: str = Field(default="USD", min_length=3, max_length=3)

    @property
    def parquet_dir(self) -> Path:
        return self.data_dir / "parquet"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def metadata_db(self) -> Path:
        return self.data_dir / "metadata.sqlite"


settings = Settings()
