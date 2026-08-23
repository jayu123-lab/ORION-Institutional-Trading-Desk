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
    orion_simulated_enabled: bool = False  # dev-only fallback, always tagged SIMULAT

    # ── Neural Strategy Settings ──────────────────────────────────────
    orion_neural_enabled: bool = True  # Activar/desactivar cerebro neural
    orion_sentiment_source: str = "fear_greed"  # fear_greed, twitter, news
    orion_technical_indicators: str = "rsi,macd,bb"  # Comma-separated list
    orion_min_profit_factor: float = 1.5  # Profit factor mínimo
    orion_min_win_rate: float = 50.0  # Win rate mínimo (%)
    orion_min_score: float = 60.0  # Score mínimo (0-100) para operar
    orion_target_markets: str = "gold,btc,eth,us500"  # Mercados objetivo (comma-sep)
    orion_spread_strategy: bool = True  # Estrategia spread Polymarket
    orion_spread_markets: str = "polymarket"  # Mercados para spread
    orion_heartbeat_interval: int = 5  # Heartbeat WS en segundos
    orion_neural_score_threshold: float = 70.0  # Umbral de decisión

    # ── Connector Settings ────────────────────────────────────────────
    orion_faro_api_key: str = ""  # API Key Faro
    orion_polymarket_ws_url: str = ""  # URL WS Polymarket (override default)

    # ── Broker Settings ───────────────────────────────────────────────
    orion_binance_api_key: str = ""  # API Key Binance
    orion_binance_secret_key: str = ""  # Secret Key Binance

    # Paper account (PAPER mode only)
    orion_starting_equity: float = 100_000.0

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()