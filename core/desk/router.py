"""Deterministic intent router — classifies every user message BEFORE any
specialist runs.

Output: RoutingDecision(intent, asset, asset_class, required_agents,
required_data, urgency). No LLM, no ambiguity: keyword + symbol tables only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# desk symbol aliases → canonical watchlist symbol
SYMBOL_ALIASES: dict[str, str] = {
    "ORO": "XAUUSD", "GOLD": "XAUUSD", "XAU": "XAUUSD",
    "PLATA": "XAGUSD", "SILVER": "XAGUSD", "XAG": "XAGUSD",
    "COBRE": "HG", "COPPER": "HG",
    "BITCOIN": "BTCUSD", "BTC": "BTCUSD", "ETH": "ETHUSD", "ETHEREUM": "ETHUSD",
    "RIPPLE": "XRPUSD", "XRP": "XRPUSD", "SOL": "SOLUSD",
    "NASDAQ": "NASDAQ", "NDX": "NDX", "SP500": "SPX", "SPX": "SPX", "ES": "ES",
    "DOW": "DJI", "DJI": "DJI", "DAX": "DAX", "IBEX": "IBEX", "FTSE": "FTSE",
    "NQ": "NQ", "VIX": "VIX", "DXY": "DXY", "US10Y": "US10Y", "US02Y": "US02Y",
    "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY",
    "CL": "CL", "OIL": "CL", "PETROLEO": "CL",
}

METAL_SYMBOLS = {"XAUUSD", "XAGUSD", "GC", "MGC", "SI", "HG"}
CRYPTO_SYMBOLS = {"BTCUSD", "ETHUSD", "XRPUSD", "SOLUSD"}
INDEX_SYMBOLS = {"SPX", "NDX", "NASDAQ", "DJI", "DAX", "IBEX", "FTSE", "ES", "NQ"}
MACRO_SYMBOLS = {"DXY", "US10Y", "US13W", "US02Y", "VIX"}

INTENTS = (
    "MARKET_ANALYSIS", "TRADE_PLAN", "MACRO", "NEWS", "RISK", "POSITIONING",
    "LIQUIDITY", "CROSS_ASSET", "CRYPTO", "METALS", "EQUITIES", "SYSTEM",
    "DESK_DEBATE",
)


def asset_class_of(symbol: str) -> str:
    s = symbol.upper()
    if s in METAL_SYMBOLS:
        return "metal"
    if s in CRYPTO_SYMBOLS:
        return "crypto"
    if s in INDEX_SYMBOLS:
        return "index"
    if s in MACRO_SYMBOLS:
        return "macro"
    return "other"


@dataclass
class RoutingDecision:
    intent: str
    asset: str | None
    asset_class: str | None
    required_agents: list[str] = field(default_factory=list)
    required_data: list[str] = field(default_factory=list)
    urgency: str = "NORMAL"

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "asset": self.asset,
            "asset_class": self.asset_class,
            "required_agents": self.required_agents,
            "required_data": self.required_data,
            "urgency": self.urgency,
        }


_CORE_PIPELINE = ["metals-analyst", "crypto-analyst", "equities-analyst"]
_ANALYSTS_FOR_ASSET = {
    "metal": ["metals-analyst"],
    "crypto": ["crypto-analyst"],
    "index": ["equities-analyst"],
}
_ALWAYS_ON = ["macro-strategist", "liquidity-analyst", "crossasset-analyst",
              "news-intelligence", "quant-architect"]


class IntentRouter:
    """Deterministic message classifier feeding the CIO pipeline."""

    _INTENT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
        ("DESK_DEBATE", ("convoca", "convoca la mesa", "debate", "mesa para", "reunir la mesa")),
        ("TRADE_PLAN", ("compraria", "comprarías", "comprar", "vender", "vendería",
                        "trade plan", "entrada", "señal", "signal", "buy", "sell",
                        "short", "long ahora")),
        ("RISK", ("riesgo", "risk", "exposicion", "exposición", "drawdown")),
        ("POSITIONING", ("cot", "cftc", "posicionamiento", "positioning",
                         "managed money", "commercials")),
        ("LIQUIDITY", ("liquidez", "liquidity", "spread")),
        ("CROSS_ASSET", ("correlacion", "correlación", "cross-asset", "cross asset",
                         "divergencia", "divergence")),
        ("NEWS", ("noticias", "news", "titulares", "headlines")),
        ("SYSTEM", ("estado del sistema", "system status", "feeds", "api offline",
                    "salud del sistema")),
        ("MARKET_ANALYSIS", ("analiza", "análisis", "analisis", "analyze", "analysis",
                             "que ves", "qué ves", "que esta haciendo", "qué está haciendo",
                             "como va", "cómo va", "vision", "visión")),
    ]

    def route(self, question: str) -> RoutingDecision:
        q = question.lower()
        asset, a_class = self.detect_asset(question)

        intent = "MARKET_ANALYSIS"  # default: user asking about the market
        for candidate, kws in self._INTENT_KEYWORDS:
            if any(kw in q for kw in kws):
                intent = candidate
                break

        # asset-flavoured intents refine when no explicit asset was named
        if asset is None and intent in ("MARKET_ANALYSIS", "TRADE_PLAN"):
            if intent == "MARKET_ANALYSIS":
                if "cripto" in q or "crypto" in q:
                    a_class = "crypto"
                elif "oro" in q or "gold" in q or "metal" in q:
                    a_class = "metal"
                elif any(w in q for w in ("nasdaq", "acciones", "indices", "índices")):
                    a_class = "index"

        required_agents = self._agents_for(intent, asset, a_class)
        required_data = self._data_for(intent, asset)
        return RoutingDecision(
            intent=intent,
            asset=asset,
            asset_class=a_class,
            required_agents=required_agents,
            required_data=required_data,
        )

    # ------------------------------------------------------------------ parts
    @staticmethod
    def detect_asset(text: str) -> tuple[str | None, str | None]:
        upper = text.upper()
        # longest alias first so BTCUSD beats BTC
        for alias in sorted(SYMBOL_ALIASES, key=len, reverse=True):
            if len(alias) >= 3 and alias in SYMBOL_ALIASES and alias in upper:
                sym = SYMBOL_ALIASES[alias]
                return sym, asset_class_of(sym)
        return None, None

    def _agents_for(self, intent: str, asset: str | None, a_class: str | None) -> list[str]:
        if intent == "SYSTEM":
            return ["market-data-engineer", "audit-agent"]
        if intent == "DESK_DEBATE":
            return [
                "metals-analyst", "crypto-analyst", "equities-analyst",
                "macro-strategist", "liquidity-analyst", "positioning-analyst",
                "crossasset-analyst", "news-intelligence", "quant-architect",
                "risk-manager", "audit-agent",
            ]
        agents: list[str] = []
        spec_class = a_class or (asset_class_of(asset) if asset else None)
        if spec_class and spec_class in _ANALYSTS_FOR_ASSET:
            agents.extend(_ANALYSTS_FOR_ASSET[spec_class])
        elif intent == "EQUITIES":
            agents.append("equities-analyst")
        elif intent == "METALS":
            agents.append("metals-analyst")
        elif intent == "CRYPTO":
            agents.append("crypto-analyst")
        elif intent == "MACRO":
            agents.append("macro-strategist")
        else:
            agents.extend(a for a in _CORE_PIPELINE if a not in agents)
        if intent == "POSITIONING":
            agents.insert(0, "positioning-analyst")
        if intent == "LIQUIDITY":
            agents.insert(0, "liquidity-analyst")
        if intent == "CROSS_ASSET":
            agents.insert(0, "crossasset-analyst")
        if intent == "NEWS":
            agents.insert(0, "news-intelligence")

        for extra in _ALWAYS_ON:
            if extra not in agents:
                agents.append(extra)

        if intent == "TRADE_PLAN" or asset is not None or intent in (
            "MARKET_ANALYSIS", "RISK", "POSITIONING", "LIQUIDITY", "CROSS_ASSET",
            "METALS", "CRYPTO", "EQUITIES", "MACRO",
        ):
            agents.extend(["risk-manager", "audit-agent"])
        # dedupe preserving order
        out: list[str] = []
        seen: set[str] = set()
        for a in agents:
            if a not in seen:
                seen.add(a)
                out.append(a)
        return out

    @staticmethod
    def _data_for(intent: str, asset: str | None) -> list[str]:
        data = ["quotes"]
        if asset is not None:
            data += ["candles", "regime", "market_brain"]
        if intent in ("CROSS_ASSET", "MARKET_ANALYSIS", "TRADE_PLAN"):
            data.append("correlations")
        if intent in ("POSITIONING", "MARKET_ANALYSIS", "TRADE_PLAN"):
            data.append("cftc_if_mapped")
        if intent != "SYSTEM":
            data.append("news_recent")
        data += ["risk_snapshot", "session_clock"]
        out: list[str] = []
        seen: set[str] = set()
        for d in data:
            if d not in seen:
                seen.add(d)
                out.append(d)
        return out
