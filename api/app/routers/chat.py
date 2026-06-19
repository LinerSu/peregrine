"""Chat endpoint — entry point for the agent harness."""
from __future__ import annotations

from fastapi import APIRouter

from ..agent import harness
from ..schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    history = [m.model_dump() for m in req.history]
    out = harness.run(req.message, history)
    return ChatResponse(reply=out["reply"], actions=out.get("actions", []))
