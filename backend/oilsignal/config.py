from pathlib import Path

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
