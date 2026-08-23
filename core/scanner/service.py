from __future__ import annotations

import asyncio
import logging
from typing import cast

from sqlalchemy import desc, select

from core.doctrine.liquidity import build_liquidity_map, detect_sweeps
from core.features.engine import calculate_features
from core.memory.models import Candle, OpportunityCandidate, Quote, utcnow
from core.notifications import notify_windows
from core.setups.library import SetupCandidate, opportunity_score, transition

logger = logging.getLogger("orion.scanner")
DEFAULT_SYMBOLS = ("XAUUSD", "MGC", "NQ", "BTCUSD", "XRPUSD")
_STATUS: dict[str, object] = {
    "running": False,
    "last_scan": None,
    "symbols": list(DEFAULT_SYMBOLS),
    "qualified": 0,
    "last_error": None,
    "cycles": 0,
}


def scanner_status() -> dict:
    return dict(_STATUS)


class OrionScanner:
    """Synchronous scan cycle plus an asyncio lifecycle wrapper."""

    def __init__(
        self,
        session_factory,
        symbols: tuple[str, ...] = DEFAULT_SYMBOLS,
        interval_seconds: float = 5.0,
    ) -> None:
        self.session_factory = session_factory
        self.symbols = symbols
        self.interval_seconds = interval_seconds
        self._stop = asyncio.Event()

    async def run_forever(self) -> None:
        _STATUS.update(running=True, symbols=list(self.symbols), last_error=None)
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception as exc:  # scanner must survive one bad symbol
                _STATUS["last_error"] = str(exc)
                logger.exception("scanner cycle failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass
        _STATUS["running"] = False

    async def stop(self) -> None:
        self._stop.set()

    def scan_once(self) -> list[dict]:
        results = []
        for symbol in self.symbols:
            result = self.scan_symbol(symbol)
            if result:
                results.append(result)
        _STATUS.update(
            last_scan=utcnow().isoformat(),
            qualified=sum(r["state"] == "CONFIRMED" for r in results),
            cycles=cast(int, _STATUS["cycles"]) + 1,
        )
        return results

    def scan_symbol(self, symbol: str) -> dict | None:
        with self.session_factory() as session:
            candles = list(
                session.execute(
                    select(Candle)
                    .where(Candle.symbol == symbol, Candle.timeframe == "H1")
                    .order_by(Candle.ts_open)
                )
                .scalars()
                .all()
            )
            quote = session.execute(
                select(Quote)
                .where(Quote.symbol == symbol)
                .order_by(desc(Quote.ts_received))
                .limit(1)
            ).scalar_one_or_none()
            if len(candles) < 5 or quote is None:
                return self._record(
                    session,
                    symbol,
                    "NO_QUALIFIED_SETUP",
                    "NEUTRAL",
                    "WATCHING",
                    0.0,
                    {},
                    {},
                    "INSUFFICIENT_DATA",
                )
            features = calculate_features(candles, symbol, "H1")
            values = {key: item.value for key, item in features.values.items()}
            atr_value = _number(values.get("atr"))
            spread = _number(values.get("di_spread"))
            adx = _number(values.get("adx"))
            adx_slope = _number(values.get("adx_slope"))
            levels = build_liquidity_map(candles, last_price=quote.price, atr=atr_value)
            sweeps = detect_sweeps(candles, levels)
            direction = "LONG" if (spread or 0) > 0 else "SHORT" if (spread or 0) < 0 else "NEUTRAL"
            setup = "LIQUIDITY_SWEEP_REVERSAL" if sweeps else "NO_QUALIFIED_SETUP"
            distance = min(
                (abs(p.price - quote.price) for p in levels.buy_side + levels.sell_side),
                default=None,
            )
            atr = atr_value or 0
            in_zone = distance is not None and (distance <= atr * 0.30 if atr else False)
            subscores = {
                "context": None,
                "location": 85 if in_zone else 35,
                "liquidity": 80 if levels.buy_side or levels.sell_side else None,
                "volume": None if values.get("volume") is None else 60,
                "order_flow": None,
                "structure": 60 if sweeps else 35,
                "trend_energy": _trend_score(adx, adx_slope, spread),
                "volatility": 60 if atr else None,
                "cross_asset": None,
                "news": None,
                "statistical_edge": None,
                "rr": None,
                "data_quality": 70 if quote.status in {"LIVE", "DELAYED"} else 20,
            }
            scored = opportunity_score(subscores, quote.status)
            setup_id = f"{symbol}:{setup}:{candles[-1].ts_open.isoformat()}"
            candidate = SetupCandidate(
                setup_id, symbol, setup, direction, score=scored["total"], features=values
            )
            transition(
                candidate,
                in_zone=in_zone,
                reaction=bool(sweeps),
                valid=quote.status not in {"STALE", "DISCONNECTED"},
                score=scored["total"],
            )
            if candidate.state == "CONFIRMED" and any(
                v is None
                for v in (subscores["order_flow"], subscores["statistical_edge"], subscores["rr"])
            ):
                candidate.state = "ARMED"
            if candidate.state == "CONFIRMED":
                notify_windows(
                    f"ORION — {symbol} {direction} CANDIDATE",
                    f"Opportunity {scored['total']:.0f} · {setup}",
                )
            return self._record(
                session,
                symbol,
                setup,
                direction,
                candidate.state,
                scored["total"],
                values,
                subscores,
                "NO QUALIFIED SETUP"
                if setup == "NO_QUALIFIED_SETUP"
                else "Awaiting statistical sample and complete confirmation",
            )

    def _record(
        self, session, symbol, setup, direction, state, score, features, subscores, reason
    ) -> dict:
        stamp = utcnow()
        setup_id = f"{symbol}:{setup}:{stamp.strftime('%Y%m%d%H%M')}"
        row = (
            session.query(OpportunityCandidate)
            .filter(OpportunityCandidate.setup_id == setup_id)
            .one_or_none()
        )
        if row is None:
            row = OpportunityCandidate(
                setup_id=setup_id, symbol=symbol, setup=setup, direction=direction
            )
            session.add(row)
        row.state, row.opportunity_score, row.features, row.subscores, row.reason, row.ts = (
            state,
            score,
            features,
            subscores,
            reason,
            stamp,
        )
        session.commit()
        return {
            "setup_id": setup_id,
            "symbol": symbol,
            "setup": setup,
            "direction": direction,
            "state": state,
            "opportunity_score": score,
            "features": features,
            "subscores": subscores,
            "reason": reason,
            "last_update": stamp.isoformat(),
        }


def _trend_score(adx, slope, spread) -> float | None:
    if adx is None or spread is None:
        return None
    return max(0.0, min(100.0, 50 + (adx - 20) * 1.2 + (slope or 0) * 3 + min(20, abs(spread))))


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None
