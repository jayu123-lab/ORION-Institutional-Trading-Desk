"""ORION Neural Strategy Engine.

Market sentiment analysis and trade signal generation using technical indicators,
fundamental factors, and proprietary scoring systems.

Design principles:
- Multi-timeframe analysis
- Weighted indicator combination
- Win-rate and profit-factor optimization
- Liquidity and volatility filtering
- Spread strategy support for Polymarket
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from core.orderbook import PolymarketOrderBookEngine

logger = logging.getLogger("orian.strategy")


# ─── Constants ───────────────────────────────────────────────────────

# Technical indicator parameters
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

BB_PERIOD = 20
BB_STD = 2.0

# Scoring weights
SCORE_WIN_RATE = 0.35
SCORE_PROFIT_FACTOR = 0.30
SCORE_MOMENTUM = 0.20
SCORE_VOLATILITY = 0.15

# Minimum thresholds
MIN_PROFIT_FACTOR = 1.5
MIN_WIN_RATE = 50.0  # percentage
MIN_SCORE = 60.0  # 0-100 scale

# Supported markets
SUPPORTED_MARKETS = [
    "gold",
    "silver",
    "btc",
    "eth",
    "usd",
    "us500",
    "us100",
    "wti",
    "natural_gas",
]

# Market categories
MARKET_CATEGORIES = [
    "crypto",
    "forex",
    "commodities",
    "indices",
]


# ─── Sentiment Analysis ──────────────────────────────────────────────

class MarketSentiment:
    """Analyzes market sentiment from various sources."""

    def __init__(self, source: str = "fear_greed") -> None:
        self.source = source
        self.last_update = datetime.now(UTC)

    def analyze(self, market_data: dict[str, Any]) -> dict[str, Any]:
        """Analyze sentiment and return score and description."""
        # Base score from source
        score = self._calculate_base_score(market_data)

        # Adjust by factors
        factors = self._calculate_factors(market_data)
        score = self._apply_factors(score, factors)

        # Clamp to 0-100
        score = max(0.0, min(100.0, score))

        return {
            "score": round(score, 1),
            "description": self._describe_sentiment(score),
            "source": self.source,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def _calculate_base_score(self, market_data: dict[str, Any]) -> float:
        """Base score from market data."""
        # Simplified: use price change, volume, etc.
        price_change = market_data.get("price_change_pct", 0.0)
        volume = market_data.get("volume", 0.0)

        # Normalized base
        base = 50.0  # Neutral start
        if price_change > 0:
            base += min(30.0, (price_change / 2.0))  # Up to +30 for strong up
        else:
            base += min(30.0, (abs(price_change) / 2.0))  # Up to -30 for strong down

        # Volume factor
        if volume > 0:
            base += 10.0 if volume > 1000 else 5.0

        return base

    def _calculate_factors(self, market_data: dict[str, Any]) -> dict[str, float]:
        """Calculate adjustment factors."""
        return {
            "trend": 0.0,
            "momentum": 0.0,
            "volatility": 0.0,
            "liquidity": 0.0,
        }

    def _describe_sentiment(self, score: float) -> str:
        """Convert score to description."""
        if score >= 80:
            return "Muy Optimista / Greed"
        elif score >= 60:
            return "Optimista"
        elif score >= 40:
            return "Neutral"
        elif score >= 20:
            return "Pesimista"
        else:
            return "Muy Pesimista / Fear"


# ─── Technical Indicators ────────────────────────────────────────────

def rsi(prices: list[float], period: int = RSI_PERIOD) -> float | None:
    """Calculate Relative Strength Index."""
    if len(prices) < period + 1:
        return None

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi_val = 100.0 - (100.0 / (1.0 + rs))
    return round(rsi_val, 2)


def macd(
    prices: list[float],
    fast_period: int = MACD_FAST,
    slow_period: int = MACD_SLOW,
    signal_period: int = MACD_SIGNAL,
) -> tuple[float | None, float | None, float | None]:
    """Calculate MACD (Moving Average Convergence Divergence)."""
    if len(prices) < slow_period:
        return None, None, None

    # Calculate EMAs
    def ema(prices_list: list[float], period: int) -> float:
        multiplier = 2.0 / (period + 1)
        ema_val = prices_list[0]
        for price in prices_list[1:]:
            ema_val = price * multiplier + ema_val * (1 - multiplier)
        return ema_val

    fast_ema = ema(prices, fast_period)
    slow_ema = ema(prices, slow_period)
    macd_line = fast_ema - slow_ema

    # Signal line from MACD histogram values
    # Simplified: use last MACD values
    signal_line = macd_line * 0.5  # Placeholder

    # Histogram
    histogram = macd_line - signal_line

    return round(macd_line, 2), round(signal_line, 2), round(histogram, 2)


def bollinger_bands(
    prices: list[float], period: int = BB_PERIOD, std_dev: float = BB_STD
) -> tuple[float | None, float | None, float | None]:
    """Calculate Bollinger Bands."""
    if len(prices) < period:
        return None, None, None

    window = prices[-period:]
    sma = sum(window) / period
    variance = sum((p - sma) ** 2 for p in window) / period
    std = variance ** 0.5

    upper = round(sma + (std_dev * std), 2)
    lower = round(sma - (std_dev * std), 2)
    middle = round(sma, 2)

    return middle, upper, lower


# ─── Scoring Engine ─────────────────────────────────────────────────

class StrategyScore:
    """Combines multiple factors into a trade signal score."""

    def __init__(
        self,
        profit_factor_weight: float = SCORE_PROFIT_FACTOR,
        win_rate_weight: float = SCORE_WIN_RATE,
        momentum_weight: float = SCORE_MOMENTUM,
        volatility_weight: float = SCORE_VOLATILITY,
    ) -> None:
        self.profit_factor_weight = profit_factor_weight
        self.win_rate_weight = win_rate_weight
        self.momentum_weight = momentum_weight
        self.volatility_weight = volatility_weight
        self._total_weight = (
            profit_factor_weight
            + win_rate_weight
            + momentum_weight
            + volatility_weight
        )

    def calculate(
        self,
        profit_factor: float,
        win_rate: float,
        momentum_score: float,
        volatility_score: float,
    ) -> dict[str, Any]:
        """Calculate composite score (0-100)."""

        # Normalize components
        pf_normalized = min(profit_factor / MIN_PROFIT_FACTOR, 1.0) * 100.0
        wr_normalized = min(win_rate / MIN_WIN_RATE, 1.0) * 100.0
        mom_normalized = min(momentum_score, 100.0)
        vol_normalized = min(volatility_score, 100.0)

        # Weighted combination
        score = (
            (pf_normalized * self.profit_factor_weight)
            + (wr_normalized * self.win_rate_weight)
            + (mom_normalized * self.momentum_weight)
            + (vol_normalized * self.volatility_weight)
        ) / self._total_weight

        # Adjust for minimum thresholds
        if profit_factor < MIN_PROFIT_FACTOR:
            score *= profit_factor / MIN_PROFIT_FACTOR
        if win_rate < MIN_WIN_RATE:
            score *= win_rate / MIN_WIN_RATE

        score = max(0.0, min(100.0, score))
        return {
            "score": round(score, 1),
            "profit_factor": round(profit_factor, 2),
            "win_rate": round(win_rate, 1),
            "momentum": round(momentum_score, 1),
            "volatility": round(volatility_score, 1),
            "meets_threshold": score >= MIN_SCORE,
        }


# ─── Market Filter ──────────────────────────────────────────────────

def is_supported_market(symbol: str) -> bool:
    """Check if market is in supported list."""
    return any(market in symbol.lower() for market in SUPPORTED_MARKETS)


def market_category(symbol: str) -> str:
    """Determine market category from symbol."""
    symbol_lower = symbol.lower()
    for category in MARKET_CATEGORIES:
        if category in symbol_lower:
            return category
    return "other"


# ─── Spread Strategy ────────────────────────────────────────────────

class SpreadStrategy:
    """Polymarket spread strategy for consistent small profits."""

    def __init__(self, min_spread_pct: float = 0.5, max_spread_pct: float = 5.0) -> None:
        self.min_spread_pct = min_spread_pct
        self.max_spread_pct = max_spread_pct

    def evaluate(
        self, ob_engine: PolymarketOrderBookEngine, token_id: str
    ) -> dict[str, Any] | None:
        """Evaluate spread opportunity for a token."""
        book = ob_engine.book(token_id)

        best_bid = book.get("best_bid")
        best_ask = book.get("best_ask")

        if best_bid is None or best_ask is None:
            return None

        # Calculate spread %
        spread = best_ask - best_bid
        spread_pct = (spread / best_bid) * 100.0 if best_bid != 0 else 0.0

        if self.min_spread_pct <= spread_pct <= self.max_spread_pct:
            return {
                "token_id": token_id,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": spread,
                "spread_pct": round(spread_pct, 2),
                "timestamp": datetime.now(UTC).isoformat(),
                "opportunity": "BUY_YES_SELL_NO",  # Buy YES at ask, Sell NO at bid
            }

        return None


# ─── Convenience ────────────────────────────────────────────────────

def analyze_market(
    symbol: str,
    prices: list[float],
    ob_engine: PolymarketOrderBookEngine | None = None,
) -> dict[str, Any]:
    """High-level market analysis combining all factors."""
    # Sentiment
    sentiment = MarketSentiment().analyze({"price_change_pct": 0.0, "volume": 1000})

    # Technical indicators
    rsi_val = rsi(prices)
    macd_line, macd_signal, macd_hist = macd(prices)
    bb_middle, bb_upper, bb_lower = bollinger_bands(prices)

    # Score (using default weights)
    scorer = StrategyScore()
    score_result = scorer.calculate(
        profit_factor=1.8,  # Would come from historical backtest
        win_rate=65.0,  # Would come from backtest
        momentum_score=(
            70.0 if rsi_val and rsi_val < 30
            else (40.0 if rsi_val and rsi_val > 70 else 50.0)
        ),
        volatility_score=65.0,
    )

    # Market filter
    supported = is_supported_market(symbol)
    category = market_category(symbol)

    # Spread evaluation (if orderbook engine provided)
    spread_opp = None
    if ob_engine:
        spread_opp = SpreadStrategy().evaluate(ob_engine, symbol.lower())

    return {
        "symbol": symbol,
        "sentiment": sentiment,
        "rsi": rsi_val,
        "macd": {"line": macd_line, "signal": macd_signal, "histogram": macd_hist},
        "bollinger": {"middle": bb_middle, "upper": bb_upper, "lower": bb_lower},
        "score": score_result,
        "supported": supported,
        "category": category,
        "spread_opportunity": spread_opp,
    }