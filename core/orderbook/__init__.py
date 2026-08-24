"""ORION Polymarket Orderbook Engine.

Maintains a real-time orderbook per token/outcome with bids/asks, best prices,
spread, depth levels, and executable pricing logic. Event-driven via WebSocket
updates. All values are MARKET MAKER prices — no assumption of fill.

Design notes:
- Thread-safe-ish (asyncio single-threaded): all mutations happen in the event loop.
- Top N configurable (default 20).
- Prices are from the executable perspective (see executable_price module).
- VWAP and fill simulation are in core/executable.py.
- Stale detection and reconnect handled by the WS manager.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from datetime import UTC, datetime

from core.config import get_settings  # noqa: F401
from core.security import get_secret_store  # noqa: F401

logger = logging.getLogger("orion.orderbook")

# ─── Constants ─────────────────────────────────────────────────────

DEFAULT_DEPTH = 20  # number of price levels to track per side
HEARTBEAT_SEC = 5
STALE_SECONDS = 30  # book considered stale if no update in this many seconds


# ─── Level Normalization ───────────────────────────────────────────

def _normalize_levels(levels_raw: list) -> list[tuple[float, float]]:
    """Normalize raw level data to List[(price, size)]. Skip invalid."""
    normalized: list[tuple[float, float]] = []
    for level in levels_raw:
        if not isinstance(level, (list, tuple)) or len(level) < 2:
            continue
        try:
            price = float(level[0])
            size = float(level[1])
            if price > 0 and size >= 0:
                normalized.append((price, size))
        except (ValueError, TypeError):
            continue
    # Sort bids high→low, asks low→high
    normalized.sort(key=lambda x: x[0], reverse=True)  # bids
    # We'll let the caller sort asks ascending if needed
    return normalized


# ─── Orderbook State ───────────────────────────────────────────────

class OrderBookLevel:
    """A single price level in the orderbook."""
    __slots__ = ("price", "size", "timestamp")

    def __init__(self, price: float, size: float = 0.0, timestamp: datetime | None = None) -> None:
        self.price = price
        self.size = size
        self.timestamp = timestamp if timestamp else datetime.now(UTC)

    def is_stale(self, now: datetime, stale_seconds: int = STALE_SECONDS) -> bool:
        return (now - self.timestamp).total_seconds() > stale_seconds


class PolymarketOrderBookEngine:
    """Orderbook engine for Polymarket markets.

    Maintains per-token orderbooks with bids/asks, best prices, spread,
    depth levels, and executable pricing logic.

    Parameters
    ----------
    max_depth : int
        Max number of price levels to track per side (default 20).
    heartbeat_sec : int
        Heartbeat interval in seconds (default 5).
    stale_sec : int
        Book staleness threshold in seconds (default 30).
    """

    def __init__(
        self,
        max_depth: int = DEFAULT_DEPTH,
        heartbeat_sec: int = HEARTBEAT_SEC,
        stale_sec: int = STALE_SECONDS,
    ) -> None:
        self.max_depth = max_depth
        self.heartbeat_sec = heartbeat_sec
        self.stale_sec = stale_sec

        # Per token_id → { "bids": OrderedDict[price→level, ...], "asks": ... }
        self._books: dict[str, dict] = {}

        self._last_update: dict[str, datetime] = {}
        self._stop = asyncio.Event()

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------

    def book(self, token_id: str) -> dict:
        """Return a copy of the current orderbook for the given token."""
        if token_id not in self._books:
            return self._empty_book(token_id)
        book = self._books[token_id]
        _ts = self._last_update.get(token_id, datetime.min.replace(tzinfo=UTC)).isoformat()
        return {
            "token_id": token_id,
            "bids": [
                {"price": level.price, "size": level.size}
                for level in book["bids"].values()
            ],
            "asks": [
                {"price": level.price, "size": level.size}
                for level in book["asks"].values()
            ],
            "best_bid": book.get("best_bid"),
            "best_ask": book.get("best_ask"),
            "spread": book.get("spread"),
            "timestamp": _ts,
            "stale": self.is_stale(token_id),
        }

    def is_stale(self, token_id: str) -> bool:
        """Return True if the book for this token has not been updated in STALE_SECONDS."""
        last = self._last_update.get(token_id)
        if last is None:
            return True
        return (datetime.now(UTC) - last).total_seconds() > self.stale_sec

    def update(
        self,
        token_id: str,
        bids: list[tuple[float, float]],
        asks: list[tuple[float, float]],
    ) -> None:
        """Update the orderbook for a token from a WS message.

        Parameters
        ----------
        token_id : str
            The market token identifier (e.g. "YES" or a contract address).
        bids : list[tuple[float, float]]
            List of (price, size) tuples, sorted high→low.
        asks : list[tuple[float, float]]
            List of (price, size) tuples, sorted low→high.
        """
        now = datetime.now(UTC)
        self._last_update[token_id] = now

        if token_id not in self._books:
            self._books[token_id] = {"bids": OrderedDict(), "asks": OrderedDict()}

        book = self._books[token_id]

        # Update bids (price → size), sorted high→low
        for price, size in bids:
            if price <= 0:
                continue
            level = book["bids"].get(price)
            if level is None:
                level = OrderBookLevel(price, size, now)
                book["bids"][price] = level
            else:
                level.size = size
                level.timestamp = now
            # Trim to max_depth
            if len(book["bids"]) > self.max_depth:
                # remove lowest bid
                lowest_price = min(book["bids"].keys())
                del book["bids"][lowest_price]

        # Update asks (price → size), sorted low→high
        for price, size in asks:
            if price <= 0:
                continue
            level = book["asks"].get(price)
            if level is None:
                level = OrderBookLevel(price, size, now)
                book["asks"][price] = level
            else:
                level.size = size
                level.timestamp = now
            # Trim to max_depth
            if len(book["asks"]) > self.max_depth:
                # remove highest ask
                highest_price = max(book["asks"].keys())
                del book["asks"][highest_price]

        # Recompute best bid/ask/spread
        self._recompute_metrics(token_id)

    def _recompute_metrics(self, token_id: str) -> None:
        """Recalculate best_bid, best_ask, spread from the book."""
        book = self._books.get(token_id)
        if not book:
            return

        bids_list = list(book["bids"].keys())
        asks_list = list(book["asks"].keys())

        best_bid = max(bids_list) if bids_list else None
        best_ask = min(asks_list) if asks_list else None

        if best_bid is not None and best_ask is not None and best_ask > best_bid:
            spread = best_ask - best_bid
        else:
            spread = None

        book["best_bid"] = best_bid
        book["best_ask"] = best_ask
        book["spread"] = spread

    def _empty_book(self, token_id: str) -> dict:
        """Return a empty-book structure for a given token."""
        self._books[token_id] = {"bids": OrderedDict(), "asks": OrderedDict()}
        self._last_update[token_id] = datetime.min.replace(tzinfo=UTC)
        return self.book(token_id)

    # ------------------------------------------------------------
    # WebSocket message parsing
    # ------------------------------------------------------------

    @staticmethod
    def parse_ws_message(raw: dict) -> dict | None:
        """Parse a WS message into (token_id, bids, asks) tuple.

        Expected WS message shape:
        {
            "token_id": "YES|NO or contract address",
            "bids": [[price, size], [price, size], ...],  // sorted high→low
            "asks": [[price, size], [price, size], ...],  // sorted low→high
            "timestamp": int|float  // epoch_ms
        }
        Returns None if the message shape is invalid.
        """
        if not isinstance(raw, dict):
            return None

        token_id = raw.get("token_id")
        if not token_id:
            return None

        bids_raw = raw.get("bids")
        asks_raw = raw.get("asks")

        if not isinstance(bids_raw, list) or not isinstance(asks_raw, list):
            return None

        # Normalize bids/asks to List[Tuple[float, float]]
        bids = _normalize_levels(bids_raw)
        asks = _normalize_levels(asks_raw)

        return {"token_id": token_id, "bids": bids, "asks": asks}

    # ─── Convenience ──────────────────────────────────────────────────

def get_orderbook(token_id: str, engine: PolymarketOrderBookEngine | None = None) -> dict:
    """Get the current orderbook for a token, creating an empty one if needed."""
    engine = engine or PolymarketOrderBookEngine()
    return engine.book(token_id)