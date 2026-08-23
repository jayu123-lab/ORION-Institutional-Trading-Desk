"""Deterministic ORION news relevance scoring and headline deduplication."""

from __future__ import annotations

import re

KEYWORDS = {
    "XAUUSD": ("gold", "bullion", "xau", "comex"),
    "NQ": ("nasdaq", "nvidia", "tech stocks", "semiconductor"),
    "SPX": ("s&p", "spx", "equities", "wall street"),
    "BTC": ("bitcoin", "btc"),
    "XRP": ("xrp", "ripple", "xrpl", "rlusd"),
    "DXY": ("dollar index", "dxy", "us dollar"),
    "RATES": ("treasury", "yield", "interest rate", "fed", "fomc"),
    "MACRO": (
        "inflation",
        "cpi",
        "pce",
        "ppi",
        "employment",
        "payroll",
        "nfp",
        "gdp",
        "claims",
        "geopolit",
    ),
}


def canonical_title(title: str) -> str:
    value = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", title.lower())).strip()
    return re.sub(r"\b(update|breaking|exclusive|analysis)\b", "", value).strip()


def score_news(title: str) -> dict:
    lowered = title.lower()
    assets = [asset for asset, words in KEYWORDS.items() if any(word in lowered for word in words)]
    score = min(100, 25 + len(assets) * 20) if assets else 0
    high_impact = any(
        word in lowered
        for word in ("fomc", "cpi", "nfp", "payroll", "rate decision", "war", "sanction")
    )
    if high_impact:
        score = min(100, score + 25)
    relevance = "CRITICAL" if score >= 85 else "HIGH" if score >= 65 else "MEDIUM"
    impact = "CATALYST" if high_impact else "RISK" if score >= 45 else "NOISE"
    return {"score": score, "assets": assets, "relevance": relevance, "impact": impact}


def filter_relevant_news(items: list, limit: int = 5) -> list[dict]:
    seen: set[str] = set()
    output: list[dict] = []
    for item in items:
        canonical = canonical_title(item.title)
        if not canonical or canonical in seen:
            continue
        scored = score_news(item.title)
        if scored["score"] < 45:
            continue
        seen.add(canonical)
        output.append(
            {
                "title": item.title,
                "source": item.source,
                "asset": ", ".join(scored["assets"]),
                "impact": scored["impact"],
                "relevance": scored["relevance"],
                "score": scored["score"],
                "ts": item.published_at.isoformat() if item.published_at else None,
            }
        )
    return sorted(output, key=lambda row: row["score"], reverse=True)[:limit]
