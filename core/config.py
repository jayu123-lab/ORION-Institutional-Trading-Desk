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
    # Both loopback forms must be allowed so the dashboard works opened as
    # http://localhost:3000 or http://127.0.0.1:3000 (browser Origin differs).
    api_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Execution safety: live requires BOTH a true flag and matching token.
    orion_live_mode: bool = False
    orion_live_confirm_token: str = ""
    tradingview_webhook_secret: str = ""

    monitor_heartbeat_seconds: int = 30
    monitor_quote_staleness_sec: int = 120

    # Embed the Polymarket RTDS WS monitor inside the API process so PRICE_UPDATE
    # events reach /ws/events without an external bus (single-node local desk).
    orion_polymarket_ws_embedded: bool = False

    # Local convenience: populate dashboard even if standalone monitor is not running.
    # Disable this when running `python -m apps.monitor.main` to avoid duplicate ingestion.
    orion_embedded_data: bool = True
    orion_embedded_quote_interval_sec: int = 60
    orion_embedded_news_interval_sec: int = 600

    # ORION UI language (P20): es default; es|en|fr|de|it|pt
    orion_ui_language: str = "es"
    orion_notification_test_mode: bool = False

    # Multi-asset feeds (see docs/DATA_SOURCES.md)
    orion_yahoo_enabled: bool = True  # indices/commodities/stocks/FX/rates (unofficial API)
    orion_coinbase_enabled: bool = True  # crypto spot majors via public exchange ticker
    orion_simulated_enabled: bool = False  # dev-only fallback, always tagged SIMULATED

    # Event bus: empty → in-process InMemoryEventBus; redis://... → RedisEventBus
    # (falls back to InMemory with a warning if the server is unreachable)
    orion_redis_url: str = ""

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
