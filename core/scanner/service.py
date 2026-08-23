"""Selective always-on opportunity scanner with strict quality gates."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import desc, select

from core.desk.registry import AgentRegistry
from core.doctrine.liquidity import LiquidityPool, build_liquidity_map, detect_sweeps
from core.features.engine import calculate_features
from core.memory.models import (
    Candle,
    OpportunityCandidate,
    OpportunityTransition,
    Quote,
    SetupStatistics,
    utcnow,
)
from core.notifications import notify_windows
from core.setups.expected_move import expected_move
from core.setups.library import opportunity_score
from core.setups.quality import SetupQualityGate

logger = logging.getLogger("orion.scanner")
DEFAULT_SYMBOLS = (
    "XAUUSD",
    "MGC",
    "GC",
    "NQ",
    "ES",
    "BTCUSD",
    "ETHUSD",
    "XRPUSD",
    "SOLUSD",
)
ACTIVE_STATES = ("WATCHING", "ARMED", "CONFIRMED", "INSUFFICIENT_DATA")
_STATUS: dict[str, object] = {
    "running": False,
    "last_scan": None,
    "symbols": list(DEFAULT_SYMBOLS),
    "qualified": 0,
    "last_error": None,
    "cycles": 0,
    "db_writes": 0,
}


def scanner_status() -> dict:
    return dict(_STATUS)


def setup_identity(
    symbol: str, setup: str, direction: str, level: float | None, session_name: str, bucket: str
) -> str:
    raw = f"{symbol}|{setup}|{direction}|{level or 0:.6f}|{session_name}|{bucket}"
    return hashlib.sha256(raw.encode("ascii")).hexdigest()[:24]


def selective_agents(symbol: str, score: float, state_changed: bool = False) -> list[str]:
    specialist = (
        "metals-analyst"
        if symbol in {"XAUUSD", "MGC", "GC"}
        else "crypto-analyst"
        if symbol in {"BTCUSD", "ETHUSD", "XRPUSD", "SOLUSD"}
        else "equities-analyst"
    )
    agents = ["market-data-engineer"]
    if score >= 60 or state_changed:
        agents += [specialist, "liquidity-analyst", "quant-architect"]
    if score >= 72 or state_changed:
        agents += ["risk-manager", "audit-agent", "orion-cio"]
    return agents


class OrionScanner:
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
        self.quality_gate = SetupQualityGate()

    async def run_forever(self) -> None:
        _STATUS.update(running=True, symbols=list(self.symbols), last_error=None)
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception as exc:
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
        results = [result for symbol in self.symbols if (result := self.scan_symbol(symbol))]
        _STATUS.update(
            last_scan=utcnow().isoformat(),
            qualified=sum(result["state"] == "CONFIRMED" for result in results),
            cycles=cast(int, _STATUS["cycles"]) + 1,
        )
        return results

    def scan_symbol(self, symbol: str) -> dict | None:
        with self.session_factory() as session:
            candles_by_tf = {tf: self._candles(session, symbol, tf) for tf in ("M5", "M15", "H1")}
            quote = session.execute(
                select(Quote)
                .where(Quote.symbol == symbol)
                .order_by(desc(Quote.ts_received))
                .limit(1)
            ).scalar_one_or_none()
            h1 = candles_by_tf["H1"]
            now = utcnow()
            session_name = _session_name(now)
            bucket = now.strftime("%Y%m%d") + f"-{session_name}"
            if quote is None or len(h1) < 5:
                setup_id = setup_identity(
                    symbol, "NO_QUALIFIED_SETUP", "NEUTRAL", None, session_name, bucket
                )
                return self._record(
                    session,
                    setup_id,
                    symbol,
                    "NO_QUALIFIED_SETUP",
                    "NEUTRAL",
                    "INSUFFICIENT_DATA",
                    0.0,
                    {},
                    {},
                    "price/history unavailable",
                )

            snapshots = {
                tf: calculate_features(rows, symbol, tf) if rows else None
                for tf, rows in candles_by_tf.items()
            }
            h1_values = _values(snapshots["H1"])
            atr = _number(h1_values.get("atr"))
            levels = build_liquidity_map(h1, last_price=quote.price, atr=atr)
            sweeps = detect_sweeps(h1, levels)
            event = sweeps[-1] if sweeps else None
            direction = "LONG" if event and event.side == "LOW" else "SHORT" if event else "NEUTRAL"
            setup = "LIQUIDITY_SWEEP_REVERSAL" if event else "NO_QUALIFIED_SETUP"
            level = (
                event.level
                if event
                else _nearest_level(levels.buy_side + levels.sell_side, quote.price)
            )
            distance = abs(quote.price - level) if level is not None else None
            normalized_distance = distance / atr if distance is not None and atr else None
            in_zone = normalized_distance is not None and normalized_distance <= 0.30
            reaction = _reaction_evidence(h1, event, direction, atr)
            entry, invalidation, target, rr = _trade_geometry(
                direction, quote.price, level, atr, h1, levels.buy_side, levels.sell_side
            )
            fresh = _fresh_quote(quote, now)
            adx_h1 = _number(h1_values.get("adx"))
            adx_slope = _number(h1_values.get("adx_slope"))
            relative_volume = _number(h1_values.get("relative_volume"))
            stat = self._statistics(session, symbol, setup)
            stat_score = _stat_score(stat)
            structure = reaction is not None
            features = {
                **h1_values,
                "adx_m5": _feature(snapshots["M5"], "adx"),
                "adx_m15": _feature(snapshots["M15"], "adx"),
                "adx_h1": adx_h1 if adx_h1 is not None else "INSUFFICIENT_DATA",
                "adx_slope": adx_slope if adx_slope is not None else "INSUFFICIENT_DATA",
                "plus_di": h1_values.get("plus_di") or "INSUFFICIENT_DATA",
                "minus_di": h1_values.get("minus_di") or "INSUFFICIENT_DATA",
                "relative_volume": relative_volume,
                "liquidity_level": level,
                "distance_to_liquidity": distance,
                "atr_normalized_distance": normalized_distance,
                "session_position": _session_position(h1, quote.price),
                "reaction": reaction,
                "entry": entry,
                "invalidation": invalidation,
                "target": target,
                "rr": rr,
                "expected_move": self._expected_move(session, symbol, setup),
                "order_flow": "NOT_AVAILABLE",
            }
            subscores = {
                "context": 55 if adx_h1 is not None else None,
                "location": _location_score(normalized_distance),
                "liquidity": 90 if event else 45 if level is not None else None,
                "volume": _volume_score(relative_volume),
                "structure": 80 if structure else 25,
                "reaction": 90 if reaction else None,
                "adx": _trend_score(adx_h1, adx_slope, _number(h1_values.get("di_spread"))),
                "volatility": 60 if atr else None,
                "cross_asset": None,
                "event_risk": 50,
                "statistical_edge": stat_score,
                "rr": min(100.0, rr * 30) if rr is not None else None,
                "data_quality": 85 if fresh and quote.status == "LIVE" else 55 if fresh else 20,
            }
            raw_score = opportunity_score(subscores, quote.status)
            gate_inputs = {
                "price": quote.price,
                "liquidity_level": level,
                "sweep_evidence": event is not None,
                "reaction_evidence": reaction,
                "atr": atr,
                "adx": adx_h1,
                "structure": structure,
                "entry_zone": in_zone,
                "entry": entry,
                "invalidation": invalidation,
                "target": target,
                "rr": rr,
                "fresh_data": fresh,
            }
            gate = self.quality_gate.evaluate(setup, gate_inputs, raw_score["total"])
            score = gate.score_cap
            state = gate.state
            if setup == "NO_QUALIFIED_SETUP":
                state = "WATCHING" if fresh else "INSUFFICIENT_DATA"
                score = min(score, 49.0)
            elif gate.passed:
                state = "CONFIRMED" if score >= 82 else "ARMED" if score >= 72 else "WATCHING"
            if state == "CONFIRMED" and quote.status != "LIVE":
                state = "ARMED"
            setup_id = setup_identity(symbol, setup, direction, level, session_name, bucket)
            reason = "; ".join(gate.reasons) or "quality gate passed"
            features["missing_inputs"] = list(gate.missing) + raw_score["missing_inputs"]
            features["statistical_edge"] = stat
            features["data_quality"] = quote.status
            previous = (
                session.query(OpportunityCandidate).filter_by(setup_id=setup_id).one_or_none()
            )
            agents = selective_agents(
                symbol, score, previous is not None and previous.state != state
            )
            features["agents_woken"] = agents
            for agent in agents:
                AgentRegistry.record_run(agent)
            self._expire_previous(session, setup_id, symbol, setup)
            result = self._record(
                session,
                setup_id,
                symbol,
                setup,
                direction,
                state,
                score,
                features,
                subscores,
                reason,
            )
            if state == "CONFIRMED" and result.get("transitioned"):
                row = session.query(OpportunityCandidate).filter_by(setup_id=setup_id).one()
                if row.risk_verdict == "GREEN_LIGHT" and row.audit_verdict == "PASS":
                    notify_windows(
                        f"ORION — {symbol} {direction} CANDIDATE",
                        f"Opportunity {score:.0f} · {setup}",
                    )
            return result

    @staticmethod
    def _candles(session, symbol: str, timeframe: str) -> list[Candle]:
        return list(
            session.execute(
                select(Candle)
                .where(Candle.symbol == symbol, Candle.timeframe == timeframe)
                .order_by(Candle.ts_open)
            )
            .scalars()
            .all()
        )

    @staticmethod
    def _statistics(session, symbol: str, setup: str) -> dict:
        row = session.execute(
            select(SetupStatistics)
            .where(SetupStatistics.symbol == symbol, SetupStatistics.setup == setup)
            .order_by(desc(SetupStatistics.ts))
            .limit(1)
        ).scalar_one_or_none()
        if row is None or row.sample_size < 30:
            return {
                "status": "INSUFFICIENT_SAMPLE",
                "sample_size": row.sample_size if row else 0,
                "win_rate": None,
                "expectancy": None,
                "average_r": None,
                "profit_factor": None,
            }
        return {
            "status": "AVAILABLE",
            "sample_size": row.sample_size,
            "win_rate": row.win_rate,
            "expectancy": row.expectancy_r,
            "average_r": row.average_r,
            "profit_factor": row.profit_factor,
        }

    @staticmethod
    def _expected_move(session, symbol: str, setup: str) -> dict:
        rows = (
            session.execute(
                select(OpportunityCandidate)
                .where(
                    OpportunityCandidate.symbol == symbol,
                    OpportunityCandidate.setup == setup,
                    OpportunityCandidate.outcome.is_not(None),
                )
                .order_by(OpportunityCandidate.ts)
            )
            .scalars()
            .all()
        )
        excursions = [
            float(row.outcome["mfe"])
            for row in rows
            if row.outcome and row.outcome.get("mfe") is not None
        ]
        return expected_move(excursions)

    def _record(
        self, session, setup_id, symbol, setup, direction, state, score, features, subscores, reason
    ) -> dict:
        stamp = utcnow()
        row = session.query(OpportunityCandidate).filter_by(setup_id=setup_id).one_or_none()
        previous_state = row.state if row else None
        if (
            row is not None
            and row.state in {"INVALIDATED", "EXPIRED"}
            and stamp - row.ts.replace(tzinfo=UTC) < timedelta(minutes=30)
        ):
            state = row.state
            reason = "cooldown active after invalidation/expiry"
        if row is None:
            row = OpportunityCandidate(
                setup_id=setup_id, symbol=symbol, setup=setup, direction=direction
            )
            session.add(row)
        changed = previous_state != state
        materially_changed = changed or row.opportunity_score != score or row.reason != reason
        heartbeat_due = row.ts is None or stamp - row.ts.replace(tzinfo=UTC) >= timedelta(
            seconds=60
        )
        if materially_changed or heartbeat_due:
            row.state, row.opportunity_score, row.features = state, score, features
            row.subscores, row.reason, row.ts = subscores, reason, stamp
            if changed:
                session.add(
                    OpportunityTransition(
                        setup_id=setup_id,
                        symbol=symbol,
                        setup=setup,
                        previous_state=previous_state,
                        new_state=state,
                        score=score,
                        reason=reason,
                    )
                )
            session.commit()
            _STATUS["db_writes"] = cast(int, _STATUS["db_writes"]) + 1
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
            "last_update": row.ts.isoformat(),
            "transitioned": changed,
        }

    @staticmethod
    def _expire_previous(session, setup_id: str, symbol: str, setup: str) -> None:
        rows = session.execute(
            select(OpportunityCandidate).where(
                OpportunityCandidate.symbol == symbol,
                OpportunityCandidate.setup == setup,
                OpportunityCandidate.setup_id != setup_id,
                OpportunityCandidate.state.in_(ACTIVE_STATES),
            )
        ).scalars().all()
        for row in rows:
            previous = row.state
            row.state = "EXPIRED"
            row.reason = "session/time bucket changed"
            session.add(OpportunityTransition(
                setup_id=row.setup_id, symbol=row.symbol, setup=row.setup,
                previous_state=previous, new_state="EXPIRED",
                score=row.opportunity_score, reason=row.reason,
            ))
        if rows:
            session.commit()


def _values(snapshot) -> dict:
    return {key: item.value for key, item in snapshot.values.items()} if snapshot else {}


def _feature(snapshot, name: str):
    value = snapshot.value(name) if snapshot else None
    return value if value is not None else "INSUFFICIENT_DATA"


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _nearest_level(pools: list[LiquidityPool], price: float) -> float | None:
    return min((pool.price for pool in pools), key=lambda value: abs(value - price), default=None)


def _reaction_evidence(
    candles: list[Candle], event, direction: str, atr: float | None
) -> str | None:
    if event is None or len(candles) < 2 or not atr:
        return None
    last, previous = candles[-1], candles[-2]
    if last.ts_open.isoformat() == event.bar_ts:
        return None
    if direction == "LONG" and last.close > previous.high and last.close - last.open >= atr * 0.25:
        return "BULLISH_DISPLACEMENT_STRUCTURE_SHIFT"
    if direction == "SHORT" and last.close < previous.low and last.open - last.close >= atr * 0.25:
        return "BEARISH_DISPLACEMENT_STRUCTURE_SHIFT"
    return None


def _trade_geometry(
    direction: str,
    price: float,
    level: float | None,
    atr: float | None,
    candles: list[Candle],
    buy: list[LiquidityPool],
    sell: list[LiquidityPool],
):
    if direction == "NEUTRAL" or level is None or not atr or not candles:
        return None, None, None, None
    entry = price
    if direction == "LONG":
        invalidation = min(candles[-1].low, level - atr * 0.25)
        targets = [pool.price for pool in buy if pool.price > entry]
        target = min(targets) if targets else None
    else:
        invalidation = max(candles[-1].high, level + atr * 0.25)
        targets = [pool.price for pool in sell if pool.price < entry]
        target = max(targets) if targets else None
    risk = abs(entry - invalidation)
    rr = abs(target - entry) / risk if target is not None and risk > 0 else None
    return entry, invalidation, target, round(rr, 3) if rr is not None else None


def _fresh_quote(quote: Quote, now: datetime) -> bool:
    stamp = (
        quote.ts_received.replace(tzinfo=UTC)
        if quote.ts_received.tzinfo is None
        else quote.ts_received
    )
    return quote.status in {"LIVE", "DELAYED"} and now - stamp <= timedelta(minutes=5)


def _session_name(now: datetime) -> str:
    hour = now.hour
    if hour < 8:
        return "ASIA"
    if hour < 13:
        return "LONDON"
    if hour < 20:
        return "NEW_YORK"
    return "AFTER_HOURS"


def _session_position(candles: list[Candle], price: float) -> float | None:
    recent = candles[-8:]
    high, low = max(c.high for c in recent), min(c.low for c in recent)
    return round((price - low) / (high - low), 3) if high > low else None


def _location_score(distance_atr: float | None) -> float | None:
    return max(0.0, 100 - distance_atr * 180) if distance_atr is not None else None


def _volume_score(relative_volume: float | None) -> float | None:
    return min(100.0, relative_volume * 60) if relative_volume is not None else None


def _trend_score(adx: float | None, slope: float | None, spread: float | None) -> float | None:
    if adx is None or spread is None:
        return None
    return max(0.0, min(100.0, 45 + (adx - 20) * 1.2 + (slope or 0) * 3 + min(20, abs(spread))))


def _stat_score(stat: dict) -> float | None:
    if stat.get("status") != "AVAILABLE" or stat.get("expectancy") is None:
        return None
    return max(0.0, min(100.0, 50 + float(stat["expectancy"]) * 20))
