"""CIO endpoints — the desk's single entry point."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from core.desk.cio import CIOOrchestrator
from core.desk.registry import AgentRegistry
from core.memory.database import get_session_factory

router = APIRouter(prefix="/api/v1/cio", tags=["cio"])

_REGISTRY: AgentRegistry | None = None
_ORCHESTRATOR: CIOOrchestrator | None = None


def get_registry() -> AgentRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = AgentRegistry()
    return _REGISTRY


def get_orchestrator() -> CIOOrchestrator:
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        _ORCHESTRATOR = CIOOrchestrator(get_session_factory(), get_registry())
    return _ORCHESTRATOR


class CioChatIn(BaseModel):
    message: str


@router.post("/chat")
async def cio_chat(payload: CioChatIn) -> dict:
    """Full desk pipeline: route → context → specialists → risk → audit → synthesis."""
    return await get_orchestrator().handle(payload.message)


@router.get("/agents")
def cio_agents() -> list[dict]:
    """Agent roster with honest dynamic status from real executions."""
    return get_registry().to_list()
