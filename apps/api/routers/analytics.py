"""Analytics endpoints: expose already-tested engines to the dashboards.

- /positioning/{symbol}   -> InstitutionalPositioningAgent (CFTC verified data)
- /cross_asset/scan       -> CrossAssetEngine over DB candles
- /market_brain/{scope}   -> MarketBrain composite state

Labels VERIFIED/DERIVED/NOT AVAILABLE are produced by the engines themselves;
this router never upgrades availability.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from core.cross_asset.engine import PAIR_SYMBOLS, CrossAssetEngine, momentum_score
from core.market_brain.brain import MarketBrain
from core.memory.database import get_session_factory
from core.memory.models import Candle, Quote
from core.positioning.agent import InstitutionalPositioningAgent

from ..deps import get_db

router = APIRouter(prefix="/api/v1", tags=["analytics"])


@router.get("/positioning/{symbol}")
async def positioning(symbol: str) -> dict:
    agent = InstitutionalPositioningAgent()
    report = await agent.report(symbol)
    return report.model_dump()


def _closes(
    session: Session, symbol: str, *, timeframe: str = "H1", limit: int = 200
) -> list[float]:
    rows = (
        session.execute(
            select(Candle.close)
            .where(Candle.symbol == symbol.upper(), Candle.timeframe == timeframe)
            .order_by(desc(Candle.ts_open))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(reversed(rows))


@router.get("/cross_asset/scan")
def cross_asset_scan(session: Session = Depends(get_db)) -> dict:
    engine = CrossAssetEngine()
    symbols_needed = sorted({s for pair_syms in PAIR_SYMBOLS.values() for s in pair_syms})
    closes_by_symbol = {sym: _closes(session, sym) for sym in symbols_needed}
    readings = engine.scan(closes_by_symbol)

    spx_mom = momentum_score(closes_by_symbol.get("SPX", []))
    btc_mom = momentum_score(closes_by_symbol.get("BTCUSD", []))

    vix_q = session.execute(
        select(Quote.price).where(Quote.symbol == "VIX").order_by(desc(Quote.ts_received)).limit(1)
    ).scalar_one_or_none()
    regime = engine.risk_regime(spx_mom, vix_q, btc_mom)

    anomalies = sum(1 for r in readings if r.is_anomaly)
    return {
        "readings": [asdict(r) for r in readings],
        "risk_regime": asdict(regime),
        "anomaly_count": anomalies,
        "note": "correlations DERIVED from DB candles; states per classify_relation thresholds",
    }


@router.get("/market_brain/{scope}")
async def market_brain(scope: str) -> dict:
    if not scope.replace("_", "").isalnum():
        raise HTTPException(status_code=422, detail="invalid scope")
    brain = MarketBrain(get_session_factory())
    state = await brain.build(scope)
    return state.to_dict()
