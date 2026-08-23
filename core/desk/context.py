"""ContextBuilder — assembles the REAL data context the CIO and specialists read.

Every field is provenance-tagged: {value, source, provenance, ts, status}.
Missing data is explicitly NOT AVAILABLE — never guessed. Special modes:

- XAUUSD (GOLD): adds GC/MGC/DXY/US10Y/VIX quotes + CFTC Gold COT.
- XRPUSD: adds BTCUSD correlation / relative strength / volatility,
  crypto news and Polymarket availability flag.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select

from core.config import get_settings
from core.market_brain.brain import MarketBrain


def tag(value, source: str | None, provenance: str = "VERIFIED",  # noqa: ANN001
        ts: str | None = None, status: str | None = None,
        extra: dict | None = None) -> dict:
    out: dict = {
        "value": value,
        "source": source,
        "provenance": provenance,
        "ts": ts or datetime.now(UTC).isoformat(),
    }
    if status is not None:
        out["status"] = status
    if extra:
        out.update(extra)
    return out


def not_available(reason: str = "no verified feed configured") -> dict:
    return {"value": None, "source": None, "provenance": "NOT_AVAILABLE",
            "ts": datetime.now(UTC).isoformat(), "reason": reason}


GOLD_EXTRA_QUOTES = ("GC", "MGC", "DXY", "US10Y", "VIX")
XRP_EXTRA_QUOTES = ("BTCUSD",)
CRYPTO_NEWS_KEYWORDS = (
    "ripple", "xrpl", "rlusd", "crypto", "bitcoin", "btc", "stablecoin",
)
METALS_NEWS_KEYWORDS = ("gold", "oro", "fed", "tariff", "inflation", "cpi", "fomc")


class ContextBuilder:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory
        self.brain = MarketBrain(session_factory)

    # ------------------------------------------------------------ public API
    async def build(self, symbol: str) -> dict:
        symbol = symbol.upper()
        ctx: dict = {"asset": symbol, "asset_class_of_interest": _class_of(symbol)}

        quote_row = self._latest_quote(symbol)
        if quote_row is not None:
            age_s = _age_seconds(quote_row.ts_received)
            stale_after = get_settings().monitor_quote_staleness_sec
            status = quote_row.status
            if status == "LIVE" and age_s > stale_after:
                status = "STALE"
            ctx["price"] = tag(
                quote_row.price, f"db:{quote_row.provider}", "VERIFIED",
                ts=quote_row.ts_received.isoformat() if quote_row.ts_received else None,
                status=status,
                extra={"bid": quote_row.bid, "ask": quote_row.ask},
            )
        else:
            ctx["price"] = not_available("no stored quote for this symbol yet")

        # --- candles summary (real stored bars, single timeframe)
        candles, tf_used = self._candles_single_tf(symbol)
        if len(candles) >= 5:
            closes = [c.close for c in candles]
            highs = [c.high for c in candles]
            lows = [c.low for c in candles]
            last_bars = candles[-14:]
            atr = _mean_true_range(last_bars) if len(last_bars) >= 2 else None
            ctx["candles"] = tag(
                {
                    "count": len(closes),
                    "last_close": closes[-1],
                    "swing_high_20": max(highs[-20:]) if len(highs) >= 20 else max(highs),
                    "swing_low_20": min(lows[-20:]) if len(lows) >= 20 else min(lows),
                    "atr": atr,
                },
                "db:candles",
                "DERIVED",
                ts=candles[-1].ts_open.isoformat(),
                extra={"timeframe": tf_used},
            )
            ctx["technicals"] = self._technicals(symbol, candles, tf_used, atr)
        else:
            ctx["candles"] = not_available(f"only {len(candles)} stored {tf_used} candles")
            ctx["technicals"] = {"session_levels": None, "liquidity": None,
                                 "orion_range_2_6": None, "sweeps": [],
                                 "reason": f"only {len(candles)} candles stored"}

        # --- market brain state (regime/momentum/vol/liquidity/macro score)
        ms = await self.brain.build(symbol)
        ctx["market_state"] = {
            "regime": ms.regime.value,
            "volatility": ms.volatility.value,
            "risk_mode": ms.risk_mode.value,
            "momentum_score": ms.momentum_score,
            "liquidity_score": ms.liquidity_score,
            "macro_score": ms.macro_score,
            "risk_score": ms.risk_score,
            "data_quality": round(ms.data_quality, 3),
            "components": [
                {"name": c.name, "value": c.value, "provenance": c.provenance.value,
                 "detail": c.detail}
                for c in ms.components
            ],
        }

        # --- cross-asset correlations from real stored closes
        pairs = _pairs_for(symbol)
        correlations: dict[str, dict] = {}
        base_closes = self.brain._closes_from_db(symbol)
        for other in pairs:
            other_closes = self.brain._closes_from_db(other)
            rho = _pearson(base_closes, other_closes)
            correlations[f"{symbol}/{other}"] = (
                tag(round(rho, 3), "cross_asset_engine:pearson", "DERIVED")
                if rho is not None
                else not_available("insufficient overlapping history")
            )
        ctx["correlations"] = correlations

        # --- relative strength for crypto vs BTC (XRP special mode)
        if symbol == "XRPUSD":
            btc_quote = self._latest_quote("BTCUSD")
            ctx["extra_quotes"] = {
                s: self._quote_tag(s) for s in XRP_EXTRA_QUOTES
            }
            if btc_quote is not None and quote_row is not None:
                ctx["relative_strength_vs_btc"] = tag(
                    round(quote_row.price / float(btc_quote.price), 6),
                    "derived:xrp_btc_ratio", "DERIVED",
                )
            else:
                ctx["relative_strength_vs_btc"] = not_available()
            ctx["polymarket"] = not_available(
                "RTDS monitor disabled; prediction-market odds not a spot feed"
            )

        # --- GOLD special mode: complex quotes + CFTC
        if symbol in ("XAUUSD", "GC", "MGC"):
            ctx["extra_quotes"] = {s: self._quote_tag(s) for s in GOLD_EXTRA_QUOTES}

        # --- CFTC positioning when a real mapping exists
        cot = await self._cftc_block(symbol)
        if cot is not None:
            ctx["positioning_cftc"] = cot
        elif any(s in symbol for s in ("BTC",)):
            cot_btc = await self._cftc_block("BTCUSD")
            ctx["positioning_cftc"] = cot_btc or not_available(
                "no CFTC series verified for this asset"
            )
        else:
            ctx["positioning_cftc"] = not_available(
                "COT weekly data not mapped for this asset"
            )

        # --- news
        keywords = None
        if _class_of(symbol) == "crypto":
            keywords = CRYPTO_NEWS_KEYWORDS
        elif _class_of(symbol) == "metal":
            keywords = METALS_NEWS_KEYWORDS
        ctx["news"] = self._recent_news(keywords)

        # --- risk snapshot
        ctx["risk_snapshot"] = self._latest_risk_snapshot()

        # --- desk clock
        from core.sessions import desk_clock

        clock = desk_clock()
        ctx["session"] = tag(
            {"utc": clock.utc.isoformat(), "active": list(clock.active_sessions)},
            "core.sessions.desk_clock", "VERIFIED",
        )

        # --- recent debates on this asset
        ctx["recent_debates"] = self._recent_debates(symbol)
        return ctx

    # ---------------------------------------------------------------- internals
    def _technicals(self, symbol: str, candles: list, tf: str, atr: float | None) -> dict:
        """P5-P8 doctrine layers derived from the SAME real candle rows."""
        try:
            from core.doctrine.liquidity import build_liquidity_map, detect_sweeps
            from core.doctrine.range26 import orion_range_zone
            from core.doctrine.session_engine import compute_session_map

            smap = compute_session_map(candles, timeframe=tf)
            session_vals = {lv.name: lv.value for lv in smap.levels
                            if lv.value is not None}
            price = self._latest_quote(symbol)
            last_price = float(price.price) if price and price.price else None
            lq = build_liquidity_map(candles, last_price, session_vals, atr)
            zone = orion_range_zone(
                candles, atr=atr, liquidity_levels=lq.all_levels(),
                session_levels=session_vals)
            return {
                "session_levels": smap.to_dict(),
                "liquidity": lq.to_dict(),
                "orion_range_2_6": zone.to_dict() if zone else None,
                "sweeps": [s.to_dict() for s in detect_sweeps(candles, lq)],
            }
        except Exception as exc:  # noqa: BLE001 — technicals must never kill context
            return {"session_levels": None, "liquidity": None,
                    "orion_range_2_6": None, "sweeps": [], "reason": str(exc)}

    def _candles_single_tf(self, symbol: str) -> tuple[list, str]:
        """Bars of ONE timeframe (H1 preferred), so ATR/structure stay coherent."""
        from core.memory.models import Candle as DBCandle

        with self.session_factory() as session:
            for tf in ("H1", "M15", "H4", "D1"):
                rows = (
                    session.execute(
                        select(DBCandle).where(DBCandle.symbol == symbol,
                                               DBCandle.timeframe == tf)
                        .order_by(desc(DBCandle.ts_open)).limit(120)
                    ).scalars().all()
                )
                if rows:
                    return sorted(rows, key=lambda r: r.ts_open), tf
        return [], "H1"

    def _quote_tag(self, symbol: str) -> dict:
        q = self._latest_quote(symbol)
        if q is None:
            return not_available(f"no stored quote for {symbol}")
        age_s = _age_seconds(q.ts_received)
        status = q.status
        if status == "LIVE" and age_s > get_settings().monitor_quote_staleness_sec:
            status = "STALE"
        return tag(q.price, f"db:{q.provider}", "VERIFIED",
                   ts=q.ts_received.isoformat() if q.ts_received else None,
                   status=status)

    def _latest_quote(self, symbol: str):
        from core.memory.models import Quote as DBQuote

        with self.session_factory() as session:
            return session.execute(
                select(DBQuote).where(DBQuote.symbol == symbol.upper())
                .order_by(desc(DBQuote.id)).limit(1)
            ).scalars().first()

    async def _cftc_block(self, symbol: str) -> dict | None:
        try:
            import httpx

            from providers.positioning.cftc import fetch_cot

            async with httpx.AsyncClient(timeout=15.0) as client:
                rec = await fetch_cot(symbol, client)
            if rec is None:
                return None
            payload: dict = {
                "report_date": rec.report_date,
                "open_interest": rec.open_interest,
                "dataset": rec.dataset,
                "note": "weekly COT snapshot — NOT intraday positioning",
            }
            if rec.managed_money_net is not None:
                payload["managed_money_net"] = rec.managed_money_net
                payload["managed_money_long"] = rec.managed_money_long
                payload["managed_money_short"] = rec.managed_money_short
            if rec.noncommercial_net is not None:
                payload["noncommercial_net"] = rec.noncommercial_net
                payload["commercial_long"] = rec.commercial_long
                payload["commercial_short"] = rec.commercial_short
            return tag(payload, "CFTC Socrata (publicreporting.cftc.gov)", "VERIFIED",
                       ts=f"{rec.report_date}T00:00:00+00:00")
        except Exception as exc:  # noqa: BLE001 - network failures must not kill the pipeline
            return not_available(f"CFTC fetch failed: {exc}")

    def _recent_news(self, keywords: tuple[str, ...] | None, limit: int = 6) -> list[dict]:
        from core.memory.models import NewsItem

        since = datetime.now(UTC) - timedelta(hours=48)
        with self.session_factory() as session:
            rows = session.execute(
                select(NewsItem).where(NewsItem.published_at >= since)
                .order_by(desc(NewsItem.published_at)).limit(120)
            ).scalars().all()
        out = []
        for r in rows:
            title_l = (r.title or "").lower()
            if keywords and not any(k in title_l for k in keywords):
                continue
            out.append(tag(r.title, f"rss:{r.source}", "VERIFIED",
                           ts=r.published_at.isoformat() if r.published_at else None,
                           extra={"relevance": r.relevance}))
            if len(out) >= limit:
                break
        return out

    def _latest_risk_snapshot(self) -> dict:
        from core.memory.models import RiskSnapshot

        with self.session_factory() as session:
            snap = session.execute(
                select(RiskSnapshot).order_by(desc(RiskSnapshot.id)).limit(1)
            ).scalars().first()
        if snap is None:
            return not_available("monitor has not written a RiskSnapshot yet")
        return tag(
            {"equity": snap.equity, "verdict": snap.verdict,
             "daily_risk_used": snap.daily_risk_used,
             "drawdown_pct": snap.drawdown_pct,
             "exposure_total": snap.exposure_total},
            "db:risk_snapshot", "VERIFIED",
        )

    def _recent_debates(self, symbol: str, limit: int = 2) -> list[dict]:
        from core.memory.models import Analysis

        with self.session_factory() as session:
            rows = session.execute(
                select(Analysis).where(Analysis.kind == "debate",
                                       Analysis.asset == symbol.upper())
                .order_by(desc(Analysis.ts)).limit(limit)
            ).scalars().all()
        return [
            {"debate_ts": r.ts.isoformat() if r.ts else None,
             "stance": r.stance, "summary": (r.output_summary or "")[:200]}
            for r in rows
        ]


# ------------------------------------------------------------------ helpers
def _class_of(symbol: str) -> str:
    from core.desk.router import asset_class_of

    return asset_class_of(symbol)


def _pairs_for(symbol: str) -> list[str]:
    s = symbol.upper()
    if s in ("XAUUSD", "GC", "MGC"):
        return ["DXY", "US10Y", "SPX"]
    if s == "XRPUSD":
        return ["BTCUSD"]
    if s in ("BTCUSD", "ETHUSD", "SOLUSD"):
        return ["SPX", "DXY"]
    if s in INDEX_SYMBOLS_SET:
        return ["US10Y", "DXY", "VIX"]
    if s == "DXY":
        return ["SPX", "XAUUSD"]
    return []


INDEX_SYMBOLS_SET = {"SPX", "NDX", "NASDAQ", "DJI", "DAX", "IBEX", "FTSE", "ES", "NQ"}


def _age_seconds(dt) -> float:  # noqa: ANN001
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - dt).total_seconds())


def _mean_true_range(rows: list) -> float | None:
    trs = []
    for prev, cur in zip(rows, rows[1:], strict=False):
        trs.append(max(cur.high - cur.low,
                       abs(cur.high - prev.close),
                       abs(cur.low - prev.close)))
    return sum(trs) / len(trs) if trs else None


def _pearson(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 10:
        return None
    x, y = a[-n:], b[-n:]
    mx, my = sum(x) / n, sum(y) / n
    vx = sum((v - mx) ** 2 for v in x)
    vy = sum((v - my) ** 2 for v in y)
    if not vx or not vy:
        return None
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y, strict=False))
    return cov / (vx ** 0.5 * vy ** 0.5)
