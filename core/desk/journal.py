"""P16 — Memory loop persistence + outcome evaluation (statistics only).

Writes every doctrine decision to DoctrineJournal; later, outcomes are
evaluated against REAL stored candles (MFE/MAE, correct bias?, correct
entry?). NO model weights are ever modified.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import desc, select

from core.memory.models import Candle, DoctrineJournal, Quote

logger = logging.getLogger("orion.journal")


def record_decision(
    session_factory,
    *,
    symbol: str,
    session_name: str | None,
    bias: str | None,
    bias_score: int | None,
    trade_quality: int | None,
    decision: str,
    entry_conditions: dict | None = None,
    liquidity_snapshot: dict | None = None,
    risk_verdict: str | None = None,
    reference_price: float | None = None,
) -> int | None:
    """Persist one decision. Returns journal id (None on DB failure)."""
    try:
        with session_factory() as session:
            row = DoctrineJournal(
                symbol=symbol.upper(), session_name=session_name,
                bias=bias, bias_score=bias_score, trade_quality=trade_quality,
                decision=decision, entry_conditions=entry_conditions,
                liquidity_snapshot=liquidity_snapshot, risk_verdict=risk_verdict,
                reference_price=reference_price, outcome_status="PENDING",
            )
            session.add(row)
            session.commit()
            return row.id
    except Exception:  # noqa: BLE001 — journaling must never break the desk
        logger.exception("could not persist doctrine journal entry")
        return None


def evaluate_journal_outcome(
    session_factory,
    journal_id: int,
    *,
    horizon_bars: int = 24,
    rr_target: float = 2.0,
) -> dict | None:
    """Evaluate a PENDING journal entry against real stored candles.

    correct_bias: did price move ≥ 0.5 ATR in the biased direction before
                  the opposite move within the horizon?
    correct_entry: would the doctrine's conditions have produced ≥ rr_target R
                   before invalidation? Only evaluated when decision == TRADE.
    """
    with session_factory() as session:
        row = session.get(DoctrineJournal, journal_id)
        if row is None or row.outcome_status != "PENDING":
            return None
        candles = session.execute(
            select(Candle).where(Candle.symbol == row.symbol, Candle.timeframe == "H1")
            .order_by(desc(Candle.ts_open)).limit(horizon_bars + 1)
        ).scalars().all()
        quote = session.execute(
            select(Quote).where(Quote.symbol == row.symbol)
            .order_by(desc(Quote.id)).limit(1)
        ).scalars().first()

        if not candles or quote is None or row.reference_price is None:
            # honest: cannot evaluate without data — stays PENDING
            return {"journal_id": journal_id, "outcome_status": "PENDING",
                    "reason": "insufficient candles/quote to evaluate"}

        candles = sorted(candles, key=lambda c: c.ts_open)
        atr_vals = []
        for prev, cur in zip(candles, candles[1:], strict=False):
            atr_vals.append(max(cur.high - cur.low,
                                abs(cur.high - prev.close),
                                abs(cur.low - prev.close)))
        atr = (sum(atr_vals) / len(atr_vals)) if atr_vals else None

        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        mfe_raw = max(highs) - row.reference_price   # favorable for LONG
        mae_raw = row.reference_price - min(lows)    # adverse for LONG

        direction = (row.bias or "").upper()
        if direction == "LONG":
            mfe, mae = mfe_raw, mae_raw
        elif direction == "SHORT":
            mfe, mae = -mae_raw, -mfe_raw
        else:
            mfe, mae = 0.0, 0.0

        threshold = (atr * 0.5) if atr and atr > 0 else 1e-12
        if direction in ("LONG", "SHORT"):
            correct_bias = bool(mfe >= threshold and mfe > abs(mae))
        else:
            correct_bias = None

        correct_entry = None
        if row.decision == "TRADE" and direction in ("LONG", "SHORT") \
                and atr and atr > 0:
            risk = atr * 1.5  # doctrine default stop distance
            target = rr_target * risk
            if direction == "LONG":
                hit_target = max(highs) >= row.reference_price + target
                hit_stop = min(lows) <= row.reference_price - risk
            else:
                hit_target = min(lows) <= row.reference_price - target
                hit_stop = max(highs) >= row.reference_price + risk
            if hit_target and not hit_stop:
                correct_entry = True
            elif hit_stop:
                correct_entry = False

        lesson = _lesson(bias=row.bias, decision=row.decision,
                         correct_bias=correct_bias, correct_entry=correct_entry)

        row.mfe = round(mfe, 6)
        row.mae = round(mae, 6)
        row.correct_bias = correct_bias
        row.correct_entry = correct_entry
        row.lesson_learned = lesson
        row.outcome_status = "EVALUATED"
        row.evaluated_at = datetime.now(UTC)
        session.commit()
        return {
            "journal_id": journal_id, "outcome_status": "EVALUATED",
            "mfe": row.mfe, "mae": row.mae,
            "correct_bias": correct_bias, "correct_entry": correct_entry,
            "lesson_learned": lesson,
        }


def _lesson(*, bias: str | None, decision: str,
            correct_bias: bool | None, correct_entry: bool | None) -> str:
    parts: list[str] = []
    if correct_bias is True:
        parts.append(f"bias {bias} aligned with subsequent movement")
    elif correct_bias is False:
        parts.append(f"bias {bias} NOT confirmed by price — context was misread "
                     "or horizon too short")
    if decision == "TRADE":
        if correct_entry is True:
            parts.append("doctrine conditions reached target before invalidation")
        elif correct_entry is False:
            parts.append("invalidation hit first — location/confirmation were weak")
    elif decision in ("WAIT", "NO_TRADE", "REJECT") and correct_bias is False:
        parts.append("WAIT was correct: no edge existed")
    elif decision in ("WAIT", "NO_TRADE", "REJECT") and correct_bias is True:
        parts.append("missed context (bias right, desk stood aside) — review quality gate")
    return "; ".join(parts) or "no actionable lesson from this sample"
