"""ExecutionGateway interface + locked live implementation (spec §11, §37).

Rules baked into code, not just policy:
- PaperTradingEngine is the default gateway.
- LiveBrokerGateway refuses to submit unless ORION_LIVE_MODE is true AND the
  caller passes the confirmation token matching ORION_LIVE_CONFIRM_TOKEN.
- No broker transport exists in Phase 1: submitting live raises loudly.
- Browser/GUI automation as an execution path is explicitly forbidden.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.config import get_settings
from core.execution.models import Fill, OrderRequest


class ExecutionGateway(ABC):
    name: str = "gateway"

    @abstractmethod
    async def submit_order(
        self, order: OrderRequest, human_token: str | None = None
    ) -> Fill | None:
        """Submit an order that has passed risk + human confirmation."""

    @abstractmethod
    async def cancel_order(self, client_order_id: str) -> bool: ...


class LiveModeDisabled(RuntimeError):
    pass


class LiveBrokerGateway(ExecutionGateway):
    """Placeholder for Phase 5 broker adapters. Locked by default."""

    name = "live"

    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def unlocked(self) -> bool:
        s = self._settings
        return bool(s.orion_live_mode and s.orion_live_confirm_token)

    async def submit_order(
        self, order: OrderRequest, human_token: str | None = None
    ) -> Fill | None:
        s = self._settings
        if not s.orion_live_mode:
            raise LiveModeDisabled("ORION_LIVE_MODE=false: live execution disabled")
        if not s.orion_live_confirm_token or human_token != s.orion_live_confirm_token:
            raise LiveModeDisabled("missing/incorrect live confirmation token")
        raise LiveModeDisabled(
            "no broker adapter installed yet (Phase 5). "
            "Implement ExecutionGateway with an official broker API first."
        )

    async def cancel_order(self, client_order_id: str) -> bool:
        raise LiveModeDisabled("ORION_LIVE_MODE=false: live execution disabled")
