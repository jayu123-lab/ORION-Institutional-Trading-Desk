"""Provider tier hierarchy (spec PRIORITY 12).

Feeds declare an institutional grade. Yahoo Finance is a real but UNOFFICIAL
public endpoint — institutional-grade LIVE is reserved for exchange/broker
feeds (Polymarket RTDS today; professional venues later).

Tiers:
- PRIMARY   : trusted for execution decisions
- SECONDARY : cross-validation reference
- FALLBACK  : usable with degraded data-quality score

Statuses refine the tier: LIVE (real-time), DELAYED, STALE, FALLBACK.
"""

from __future__ import annotations

from enum import StrEnum


class FeedTier(StrEnum):
    PRIMARY = "PRIMARY_FEED"
    SECONDARY = "SECONDARY_FEED"
    FALLBACK = "FALLBACK_FEED"


class FeedGrade(StrEnum):
    INSTITUTIONAL_LIVE = "LIVE"
    DELAYED = "DELAYED"
    UNOFFICIAL = "UNOFFICIAL"  # public endpoints without contractual guarantees
    SIMULATED = "SIMULATED"


# provider name -> (tier, grade). Configurable via config/feed_tiers.json
DEFAULT_TIERS: dict[str, tuple[FeedTier, FeedGrade]] = {
    "polymarket-rtds": (FeedTier.PRIMARY, FeedGrade.INSTITUTIONAL_LIVE),
    "yahoo": (FeedTier.SECONDARY, FeedGrade.UNOFFICIAL),
    "cftc": (FeedTier.SECONDARY, FeedGrade.DELAYED),  # official, weekly cadence
    "simulated": (FeedTier.FALLBACK, FeedGrade.SIMULATED),
}

TIER_CONFIG_PATHS = ("config/feed_tiers.json",)


def load_tiers(path: str | None = None) -> dict[str, tuple[FeedTier, FeedGrade]]:
    """Load provider tiers from config JSON if present, else defaults.

    JSON shape: {"polymarket-rtds": ["PRIMARY_FEED", "LIVE"], ...}
    Unknown providers in config are ignored (must be registered in code).
    """
    import json
    from pathlib import Path

    tiers = dict(DEFAULT_TIERS)
    candidates = [Path(path)] if path else [Path(p) for p in TIER_CONFIG_PATHS]
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for name, pair in data.items():
            if name not in DEFAULT_TIERS:
                continue  # providers must be registered in code before tiering
            try:
                tiers[name] = (FeedTier(pair[0]), FeedGrade(pair[1]))
            except (ValueError, KeyError, IndexError):
                continue
        break
    return tiers


def status_from_grade(grade: FeedGrade) -> str:
    """Map feed grade to the user-facing DataStatus string."""
    mapping = {
        FeedGrade.INSTITUTIONAL_LIVE: "LIVE",
        FeedGrade.DELAYED: "DELAYED",
        FeedGrade.UNOFFICIAL: "DELAYED",  # unofficial public API: treat as delayed-grade
        FeedGrade.SIMULATED: "SIMULATED",
    }
    return mapping[grade]
