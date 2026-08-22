"""Desk Room chat: @mentions routing to data-backed responders + history."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from agents.base import BaseResponder
from agents.desk import build_responders
from apps.api.deps import get_db
from core.memory.models import ChatMessage, utcnow

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

_RESPONDERS: dict[str, BaseResponder] | None = None


def responders() -> dict[str, BaseResponder]:
    global _RESPONDERS
    if _RESPONDERS is None:
        _RESPONDERS = build_responders()
    return _RESPONDERS


class ChatIn(BaseModel):
    content: str
    room: str = "desk"  # desk | agent:<name>


class ChatOut(ChatIn):
    id: int
    author: str
    ts: str


@router.post("", response_model=ChatOut, status_code=201)
def send_message(msg: ChatIn, session: Session = Depends(get_db)) -> ChatOut:
    mentions = re.findall(r"@(\w[\w-]*)", msg.content)
    user_row = ChatMessage(room=msg.room, author="user", content=msg.content, mentions=mentions)
    session.add(user_row)
    session.flush()

    reply_text: str
    if mentions:
        target = mentions[0]
        responder = responders().get(target)
        if responder is None:
            known = ", ".join(sorted(responders()))
            reply_text = f"Agente '@{target}' no existe en la mesa. Agentes: {known}"
            author = "system"
        else:
            reply = responder.respond(msg.content, session)
            reply_text = reply.content
            author = reply.agent
    else:
        cio = responders()["orion-cio"]
        reply_text = cio.respond(msg.content, session).content
        author = "orion-cio"

    bot_row = ChatMessage(room=msg.room, author=author, content=reply_text)
    session.add(bot_row)
    session.commit()

    return ChatOut(
        id=user_row.id,
        room=msg.room,
        author="user",
        content=msg.content,
        ts=str(utcnow()),
    )


@router.get("/history")
def history(room: str = "desk", limit: int = 50, session: Session = Depends(get_db)) -> list[dict]:
    rows = (
        session.execute(
            select(ChatMessage)
            .where(ChatMessage.room == room)
            .order_by(desc(ChatMessage.ts))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {"id": r.id, "author": r.author, "content": r.content, "ts": str(r.ts)}
        for r in reversed(rows)
    ]


@router.get("/agents")
def list_agents() -> dict:
    return {"agents": sorted(responders()), "llm_agents": ".opencode/agents/"}
