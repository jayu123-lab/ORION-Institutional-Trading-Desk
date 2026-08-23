"""Central configuration via pydantic-settings. Secrets only from environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    orion_env: str = "development"
    log_level: str = "INFO"

    database_url: str = "sqlite:///./data/orion.db"
    data_dir: str = "./data"

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_cors_origins: str = "http://localhost:3000"

    # Execution safety: live requires BOTH a true flag and matching token.
    orion_live_mode: bool = False
    orion_live_confirm_token: str = ""
    tradingview_webhook_secret: str = ""

    monitor_heartbeat_seconds: int = 30
    monitor_quote_staleness_sec: int = 120

    # Embed the Polymarket RTDS WS monitor inside the API process so PRICE_UPDATE
    # events reach /ws/events without an external bus (single-node local desk).
    orion_polymarket_ws_embedded: bool = False

    # Paper account (PAPER mode only)
    orion_starting_equity: float = 100_000.0

    polymarket_gamma_base_url: str = "https://gamma-api.polymarket.com"
    polymarket_clob_base_url: str = "https://clob.polymarket.com"
    polymarket_ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
