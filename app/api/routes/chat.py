"""Chat endpoint - core interaction."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Message, Session
from app.schemas.chat import ChatRequest, ChatResponse, MessageResponse
from app.services.chat import ChatService

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """
    Send a message to the active agent and get a response.

    The arbiter processes the witness response, extracts facts,
    checks for contradictions, and the agent generates a follow-up question.
    """
    # Verify session exists and is active
    result = await db.execute(select(Session).where(Session.id == request.session_id))
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != "active":
        raise HTTPException(status_code=400, detail="Session is not active")

    # Process the chat
    service = ChatService(db)
    try:
        response = await service.process_message(
            session_id=request.session_id,
            witness_message=request.message,
            agent_mode=session.agent_mode,
            profile_id=session.profile_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Processing error: {exc}") from exc

    return response


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[MessageResponse]:
    """Get all messages for a session."""
    # Verify session exists
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get messages
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    )
    messages = result.scalars().all()

    return [
        MessageResponse(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            citations=msg.citations,
            arbiter_flags=msg.arbiter_flags,
            truth_score=msg.truth_score,
            created_at=msg.created_at.isoformat(),
        )
        for msg in messages
    ]
