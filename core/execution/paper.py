"""Paper trading engine (spec §36): imperfect fills by design.

Models spread cost, ATR-based slippage, commission and partial fills with a
seeded RNG so runs are reproducible. Never assumes a perfect fill at last price.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from core.execution.models import Fill, OrderRequest
from core.market_data.base import Quote


@dataclass(frozen=True)
class PaperConfig:
    commission_bps: float = 2.0  # per side, of notional
    slippage_atr_fraction: float = 0.05  # fraction of daily-ish range proxy
    partial_fill_probability: float = 0.15
    partial_fill_min_fraction: float = 0.5
    seed: int | None = 42


class PaperTradingEngine:
    def __init__(self, config: PaperConfig | None = None) -> None:
        self.config = config or PaperConfig()
        self._rng = random.Random(self.config.seed)

    def simulate_fill(
        self,
        order: OrderRequest,
        quote: Quote,
        reference_range: float | None = None,
    ) -> Fill:
        """
        quote: fresh quote to price against (must not be stale — caller checks).
        reference_range: e.g. recent candle high-low; defaults to 10 bps of price.
        """
        if quote.quality.status.value == "STALE":
            raise ValueError("refusing paper fill on stale quote")

        mid = quote.price
        half_spread = ((quote.ask - quote.bid) / 2) if (quote.ask and quote.bid) else mid * 0.0001

        rng_proxy = reference_range if reference_range else mid * 0.001
        slip = abs(self._rng.gauss(0, self.config.slippage_atr_fraction * rng_proxy))

        direction = 1 if order.side.value == "BUY" else -1
        raw_price = mid + direction * (half_spread + slip)

        # limit orders only fill at limit-or-better; otherwise pending → no fill now
        if order.order_type.value == "LIMIT":
            lp = order.limit_price or mid
            touchable = (order.side.value == "BUY" and mid <= lp) or (
                order.side.value == "SELL" and mid >= lp
            )
            if not touchable:
                raise ValueError("limit not touchable at current quote: order remains working")
            fill_price = min(raw_price, lp) if order.side.value == "BUY" else max(raw_price, lp)
        else:
            fill_price = raw_price

        qty = order.qty
        if self._rng.random() < self.config.partial_fill_probability:
            qty = round(
                order.qty * self._rng.uniform(self.config.partial_fill_min_fraction, 0.95), 8
            )

        slippage_bps = abs(fill_price - mid) / mid * 10_000
        commission = fill_price * qty * self.config.commission_bps / 10_000

        return Fill(
            qty=qty,
            price=round(fill_price, 6),
            commission=round(commission, 6),
            slippage_bps=round(slippage_bps, 2),
        )
