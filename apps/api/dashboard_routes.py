"""FastAPI routes for ORION Dashboard."""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "ORION Dashboard",
        "version": "1.0.0",
    }


@router.get("/widgets")
async def get_widgets():
    """Get all dashboard widgets."""
    return {
        "widgets": [
            {
                "id": "market_status",
                "type": "metric",
                "title": "Market Status",
                "data": {"status": "LIVE", "feeds": 7, "degraded": 0},
            },
            {
                "id": "vix_gauge",
                "type": "gauge",
                "title": "VIX Level",
                "data": {"value": 18.5, "min": 10, "max": 50, "status": "normal"},
            },
            {
                "id": "volume_table",
                "type": "table",
                "title": "Top Volume",
                "data": {
                    "headers": ["Symbol", "Volume", "Price", "Notional"],
                    "rows": [
                        ["SPY", "45.2M", "450.25", "$20.3B"],
                        ["QQQ", "32.1M", "375.50", "$12.0B"],
                        ["BTC", "28.5B", "45000", "$1.28T"],
                    ],
                },
            },
            {
                "id": "economic_events",
                "type": "alert",
                "title": "Next Event",
                "data": {
                    "message": "🔴 Fed Interest Rate Decision in 45 minutes",
                    "level": "warning",
                },
            },
            {
                "id": "bias_metric",
                "type": "metric",
                "title": "Market Bias",
                "data": {"bias": "BULLISH", "confidence": 0.78, "specialists": 9},
            },
        ]
    }


@router.get("/market-overview")
async def market_overview():
    """Get market overview data."""
    return {
        "timestamp": "2026-08-27T10:30:00Z",
        "indices": {
            "SPX": {"price": 5450.25, "change": "+0.75%", "status": "LIVE"},
            "NDX": {"price": 19230.50, "change": "+1.20%", "status": "LIVE"},
            "INDU": {"price": 42150.75, "change": "+0.50%", "status": "LIVE"},
        },
        "yields": {
            "US2Y": 4.25,
            "US10Y": 4.15,
            "US30Y": 4.35,
            "status": "LIVE",
        },
        "volatility": {
            "VIX": 18.5,
            "regime": "normal",
            "status": "LIVE",
        },
    }


@router.get("/specialist-inputs")
async def specialist_inputs():
    """Get specialist consensus inputs."""
    return {
        "specialists": 9,
        "macro": {
            "bias": "STRONG_BULLISH",
            "confidence": 0.82,
            "narrative": "Fed pause supports equities",
        },
        "liquidity": {
            "ok": True,
            "depth": "wide",
            "spreads": "tight",
        },
        "technical": {
            "trend": "UP",
            "momentum": 65,
            "support": 5400,
            "resistance": 5500,
        },
        "risk_score": 35,
        "timestamp": "2026-08-27T10:30:00Z",
    }


@router.get("/decisions/pending")
async def pending_decisions():
    """Get pending trade decisions."""
    return {
        "pending": [
            {
                "asset": "SPY",
                "decision": "LONG",
                "confidence": 0.85,
                "entry": 450.25,
                "stop_loss": 441.25,
                "target": 468.50,
                "risk_reward": 2.1,
                "status": "AWAITING_APPROVAL",
                "risk_approved": False,
            },
            {
                "asset": "GLD",
                "decision": "WAIT",
                "confidence": 0.62,
                "rationale": "Conflicting signals between macro and technical",
                "status": "MONITORING",
            },
        ],
        "approved": 3,
        "rejected": 1,
    }


@router.get("/decisions/executed")
async def executed_decisions():
    """Get recently executed decisions."""
    return {
        "today": [
            {
                "asset": "QQQ",
                "decision": "LONG",
                "entry": 375.50,
                "current": 378.25,
                "pnl": "+$275",
                "timestamp": "2026-08-27T09:15:00Z",
                "status": "OPEN",
            },
            {
                "asset": "GC",
                "decision": "LONG",
                "entry": 2432.50,
                "current": 2435.75,
                "pnl": "+$162.50",
                "timestamp": "2026-08-27T08:45:00Z",
                "status": "OPEN",
            },
        ],
        "total_trades": 5,
        "winning_trades": 4,
        "win_rate": 0.80,
    }


@router.get("/risk-dashboard")
async def risk_dashboard():
    """Get risk management dashboard."""
    return {
        "daily_pnl": "+$2,450",
        "daily_loss_limit": "-$2,000 (2%)",
        "remaining_loss": "$450",
        "positions": 2,
        "max_drawdown": "-1.2%",
        "leverage": 1.0,
        "alerts": [
            {
                "type": "WARNING",
                "message": "Correlation spike detected between SPY and GLD",
                "level": "MEDIUM",
            },
        ],
    }


@router.get("/economic-calendar")
async def economic_calendar():
    """Get economic calendar events."""
    return {
        "events": [
            {
                "time": "12:30 UTC",
                "country": "US",
                "event": "Fed Interest Rate Decision",
                "impact": "HIGH",
                "forecast": "4.25%",
                "previous": "4.25%",
                "status": "UPCOMING",
            },
            {
                "time": "13:00 UTC",
                "country": "US",
                "event": "FOMC Press Conference",
                "impact": "HIGH",
                "status": "UPCOMING",
            },
            {
                "time": "14:45 UTC",
                "country": "EUR",
                "event": "Eurozone CPI",
                "impact": "MEDIUM",
                "forecast": "2.5%",
                "previous": "2.6%",
                "status": "UPCOMING",
            },
        ],
        "next_high_impact": 45,  # minutes until next high impact event
    }


@router.get("/volume-monitor")
async def volume_monitor():
    """Get volume monitoring data."""
    return {
        "monitored_assets": ["SPY", "QQQ", "GLD", "BTC", "ETH"],
        "volume_data": [
            {
                "symbol": "SPY",
                "volume": "45.2M",
                "avg_volume": "38.5M",
                "spike_factor": 1.17,
                "status": "normal",
            },
            {
                "symbol": "BTC",
                "volume": "28.5B USD",
                "avg_volume": "24.3B USD",
                "spike_factor": 1.17,
                "status": "normal",
            },
        ],
    }


@router.get("/llm-agent/stats")
async def llm_agent_stats():
    """Get LLM decision agent statistics."""
    return {
        "model": "claude-opus",
        "total_decisions": 127,
        "long": 45,
        "short": 28,
        "wait": 54,
        "avg_confidence": 0.78,
        "last_decision": {
            "asset": "SPY",
            "decision": "LONG",
            "confidence": 0.85,
            "timestamp": "2026-08-27T10:25:00Z",
        },
    }


@router.get("/system-status")
async def system_status():
    """Get overall system health."""
    return {
        "services": {
            "api": {"status": "HEALTHY", "uptime": "23h 45m"},
            "database": {"status": "HEALTHY", "queries": 1250},
            "event_bus": {"status": "HEALTHY", "events": 5420},
            "feeds": {
                "yahoo": {"status": "LIVE", "last_update": "10:29:58Z"},
                "coingecko": {"status": "LIVE", "last_update": "10:29:55Z"},
                "fred": {"status": "LIVE", "last_update": "10:00:00Z"},
            },
        },
        "data_quality": {
            "nasdaq": "LIVE",
            "crypto": "LIVE",
            "forex": "LIVE",
            "bonds": "LIVE",
            "commodities": "LIVE",
        },
        "alerts": 2,
        "timestamp": "2026-08-27T10:30:00Z",
    }
