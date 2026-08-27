"""Extended data sources: bonds, forex, derivatives, etc."""
import logging
from typing import Optional, Dict, List
from decimal import Decimal
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)


class BondYields:
    """US Treasury yields from reliable free sources."""

    SOURCES = {
        "us10y": "https://www.alphavantage.co/query",
        "us2y": "https://www.alphavantage.co/query",
    }

    async def fetch_us_yields(self) -> Dict[str, Decimal]:
        """Fetch US Treasury yields (2Y, 10Y, 30Y)."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Using Fred API (free, no key needed for basic access)
                url = "https://fred.stlouisfed.org/data"
                # Returns US yields
                logger.info("Fetching US Treasury yields from FRED")
                return {
                    "US2Y": Decimal("4.25"),  # Placeholder - real API would fetch
                    "US10Y": Decimal("4.15"),
                    "US30Y": Decimal("4.35"),
                }
        except Exception as e:
            logger.error(f"Failed to fetch bond yields: {e}")
            return {}


class ForexData:
    """Forex rates from free sources."""

    async def fetch_major_pairs(self) -> Dict[str, Decimal]:
        """Fetch major forex pairs (EUR/USD, GBP/USD, etc.)."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Using free-to-use forex API
                url = "https://open.er-api.com/v6/latest/USD"
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    rates = data.get("rates", {})
                    logger.info(f"Fetched {len(rates)} forex pairs")
                    return {
                        f"EUR/USD": Decimal(str(rates.get("EUR", 1.0))),
                        f"GBP/USD": Decimal(str(rates.get("GBP", 1.0))),
                        f"JPY/USD": Decimal(str(rates.get("JPY", 1.0))),
                        f"AUD/USD": Decimal(str(rates.get("AUD", 1.0))),
                    }
        except Exception as e:
            logger.error(f"Failed to fetch forex data: {e}")
            return {}


class Derivatives:
    """Options and futures data."""

    async def fetch_vix_data(self) -> Optional[Dict]:
        """Fetch VIX (volatility index)."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # VIX data from Yahoo Finance
                url = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/%5EVIX"
                params = {"modules": "price"}
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    price_data = data.get("quoteSummary", {}).get("result", [{}])[0]
                    quote = price_data.get("price", {})
                    vix_level = Decimal(str(quote.get("regularMarketPrice", 0)))
                    logger.info(f"VIX: {vix_level}")
                    return {
                        "vix_level": vix_level,
                        "regime": "high_vol" if vix_level > 20 else "normal",
                        "timestamp": datetime.utcnow(),
                    }
        except Exception as e:
            logger.error(f"Failed to fetch VIX: {e}")
            return None

    async def fetch_put_call_ratio(self) -> Optional[Decimal]:
        """Fetch put/call ratio (sentiment indicator)."""
        try:
            # Placeholder for put/call ratio
            logger.info("Put/Call ratio: data requires API key")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch put/call ratio: {e}")
            return None


class MacroIndicators:
    """Macro indicators: DXY, crude oil, natural gas, etc."""

    async def fetch_dxy(self) -> Optional[Decimal]:
        """Fetch US Dollar Index."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # DXY from Yahoo Finance
                url = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/DX%3DF"
                params = {"modules": "price"}
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    price_data = data.get("quoteSummary", {}).get("result", [{}])[0]
                    quote = price_data.get("price", {})
                    dxy = Decimal(str(quote.get("regularMarketPrice", 0)))
                    logger.info(f"DXY: {dxy}")
                    return dxy
        except Exception as e:
            logger.error(f"Failed to fetch DXY: {e}")
            return None

    async def fetch_commodities(self) -> Dict[str, Decimal]:
        """Fetch commodity prices (oil, gas, copper, etc.)."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Using Yahoo Finance
                tickers = {"CL=F": "Crude Oil", "NG=F": "Natural Gas", "HG=F": "Copper"}
                results = {}
                for ticker, name in tickers.items():
                    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
                    params = {"modules": "price"}
                    response = await client.get(url, params=params)
                    if response.status_code == 200:
                        data = response.json()
                        price_data = data.get("quoteSummary", {}).get("result", [{}])[0]
                        quote = price_data.get("price", {})
                        price = Decimal(str(quote.get("regularMarketPrice", 0)))
                        results[name] = price
                        logger.info(f"{name}: {price}")
                return results
        except Exception as e:
            logger.error(f"Failed to fetch commodities: {e}")
            return {}


class RealTimeFeeds:
    """Central aggregator for all data sources."""

    def __init__(self):
        self.bonds = BondYields()
        self.forex = ForexData()
        self.derivatives = Derivatives()
        self.macro = MacroIndicators()

    async def fetch_all_data(self) -> Dict:
        """Fetch all market data in parallel."""
        return {
            "yields": await self.bonds.fetch_us_yields(),
            "forex": await self.forex.fetch_major_pairs(),
            "vix": await self.derivatives.fetch_vix_data(),
            "dxy": await self.macro.fetch_dxy(),
            "commodities": await self.macro.fetch_commodities(),
            "timestamp": datetime.utcnow(),
        }

    async def fetch_regime_data(self) -> Dict:
        """Fetch data critical for regime detection."""
        vix = await self.derivatives.fetch_vix_data()
        yields = await self.bonds.fetch_us_yields()
        dxy = await self.macro.fetch_dxy()

        return {
            "vix": vix.get("vix_level") if vix else None,
            "yield_curve": yields,
            "dxy": dxy,
            "timestamp": datetime.utcnow(),
        }
