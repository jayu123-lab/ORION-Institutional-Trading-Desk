from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
import httpx
from decimal import Decimal

logger = logging.getLogger(__name__)


class VolumeSnapshot:
    """Represents a volume snapshot at a point in time."""

    def __init__(
        self,
        symbol: str,
        volume: Decimal,
        price: Decimal,
        timestamp: datetime,
        source: str,
        notional: Optional[Decimal] = None,
    ):
        self.symbol = symbol
        self.volume = volume
        self.price = price
        self.timestamp = timestamp
        self.source = source
        self.notional = notional or (volume * price)

    def volume_sma(self, period: int = 20) -> Optional[Decimal]:
        """Calculate SMA of volume (requires historical data)."""
        return None  # Requires more snapshots


class VolumeMonitor:
    """Monitors trading volume from free, reliable sources."""

    # Free data sources
    SOURCES = {
        "yahoo": "https://query1.finance.yahoo.com",
        "coingecko": "https://api.coingecko.com/api/v3",
    }

    def __init__(self):
        self.snapshots: Dict[str, List[VolumeSnapshot]] = {}
        self.last_update: Dict[str, datetime] = {}

    async def fetch_stock_volume(self, symbol: str) -> Optional[VolumeSnapshot]:
        """Fetch stock volume from Yahoo Finance (free, no API key required)."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Yahoo Finance API endpoint
                url = f"{self.SOURCES['yahoo']}/v10/finance/quoteSummary/{symbol}"
                params = {"modules": "price"}

                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    price_data = data.get("quoteSummary", {}).get("result", [{}])[0]
                    quote = price_data.get("price", {})

                    volume = Decimal(str(quote.get("regularMarketVolume", 0)))
                    price = Decimal(str(quote.get("regularMarketPrice", 0)))

                    snapshot = VolumeSnapshot(
                        symbol=symbol,
                        volume=volume,
                        price=price,
                        timestamp=datetime.utcnow(),
                        source="yahoo",
                    )
                    self._store_snapshot(symbol, snapshot)
                    logger.info(f"Fetched volume for {symbol}: {volume}")
                    return snapshot
        except Exception as e:
            logger.error(f"Failed to fetch stock volume for {symbol}: {e}")
        return None

    async def fetch_crypto_volume(self, crypto_id: str = "bitcoin") -> Optional[VolumeSnapshot]:
        """Fetch crypto volume from CoinGecko (free, no API key required)."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                url = f"{self.SOURCES['coingecko']}/simple/price"
                params = {
                    "ids": crypto_id,
                    "vs_currencies": "usd",
                    "include_market_cap": "true",
                    "include_24hr_vol": "true",
                    "include_last_updated_at": "true",
                }

                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    crypto_data = data.get(crypto_id, {})

                    volume_24h = Decimal(str(crypto_data.get("usd_24h_vol", 0)))
                    price = Decimal(str(crypto_data.get("usd", 0)))

                    snapshot = VolumeSnapshot(
                        symbol=crypto_id.upper(),
                        volume=volume_24h,
                        price=price,
                        timestamp=datetime.utcnow(),
                        source="coingecko",
                    )
                    self._store_snapshot(crypto_id.upper(), snapshot)
                    logger.info(f"Fetched 24h volume for {crypto_id}: ${volume_24h}")
                    return snapshot
        except Exception as e:
            logger.error(f"Failed to fetch crypto volume for {crypto_id}: {e}")
        return None

    def _store_snapshot(self, symbol: str, snapshot: VolumeSnapshot):
        """Store volume snapshot in memory."""
        if symbol not in self.snapshots:
            self.snapshots[symbol] = []

        # Keep only last 100 snapshots per symbol (limit memory)
        self.snapshots[symbol].append(snapshot)
        if len(self.snapshots[symbol]) > 100:
            self.snapshots[symbol].pop(0)

        self.last_update[symbol] = datetime.utcnow()

    def get_latest_volume(self, symbol: str) -> Optional[VolumeSnapshot]:
        """Get latest volume snapshot for a symbol."""
        if symbol in self.snapshots and self.snapshots[symbol]:
            return self.snapshots[symbol][-1]
        return None

    def get_volume_history(self, symbol: str, hours: int = 24) -> List[VolumeSnapshot]:
        """Get volume snapshots from last X hours."""
        if symbol not in self.snapshots:
            return []

        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return [s for s in self.snapshots[symbol] if s.timestamp >= cutoff]

    def is_volume_spike(self, symbol: str, threshold: float = 1.5) -> bool:
        """Check if current volume is above average (requires history)."""
        history = self.get_volume_history(symbol, hours=24)
        if len(history) < 5:
            return False

        latest = history[-1].volume
        avg = sum(s.volume for s in history[:-1]) / (len(history) - 1)
        return float(latest) > float(avg) * threshold

    def get_monitored_symbols(self) -> List[str]:
        """Get all monitored symbols."""
        return list(self.snapshots.keys())

    def format_volume_report(self, symbol: str) -> str:
        """Format volume data for display."""
        latest = self.get_latest_volume(symbol)
        if not latest:
            return f"No data for {symbol}"

        lines = [f"Volume Report: {symbol}"]
        lines.append(f"Timestamp: {latest.timestamp.isoformat()}")
        lines.append(f"Volume: {latest.volume:,.0f}")
        lines.append(f"Price: ${latest.price}")
        lines.append(f"Notional: ${latest.notional:,.0f}")
        lines.append(f"Source: {latest.source}")

        if self.is_volume_spike(symbol):
            lines.append("⚠️  VOLUME SPIKE DETECTED")

        return "\n".join(lines)
