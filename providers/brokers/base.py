"""Broker adapter interfaces (Phase 5). NO live transport is implemented here.

Any real broker integration must:
1. Verify the broker's official API docs first (record URL + date).
2. Subclass ExecutionGateway (core/execution/gateway.py), not bypass it.
3. Respect the human-approval flow; never accept orders from analyst agents.
4. Use credentials from environment only.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrokerCapability:
    supports_market: bool
    supports_limit: bool
    supports_stop: bool
    paper_account: bool


class BrokerAdapterBase:
    """Common surface for IBKR / Alpaca / OANDA / Binance-style adapters."""

    name: str = "base"
    capabilities: BrokerCapability

    async def healthcheck(self) -> bool:  # pragma: no cover - interface
        raise NotImplementedError("broker adapters arrive in Phase 5")
