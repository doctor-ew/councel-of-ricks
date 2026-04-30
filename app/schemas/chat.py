"""Chat-related schemas."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class Citation(BaseModel):
    """Schema for document citation."""

    document_id: UUID
    document_name: str
    page_number: int
    excerpt: str


class ArbiterFlag(BaseModel):
    """Schema for arbiter-raised flags."""

    flag_type: Literal["contradiction", "unsupported", "vague", "risk"]
    description: str
    related_fact_ids: list[UUID] = []


class ChatRequest(BaseModel):
    """Schema for chat request."""

    session_id: UUID
    message: str


class ChatResponse(BaseModel):
    """Schema for chat response."""

    agent_message: str
    citations: list[Citation]
    arbiter_flags: list[ArbiterFlag]
    new_facts: list[UUID]
    truth_score: int  # 0-100, computed deterministically by arbiter


class MessageResponse(BaseModel):
    """Schema for message in history."""

    id: UUID
    role: str
    content: str
    citations: list[Citation]
    arbiter_flags: list[ArbiterFlag]
    truth_score: int | None = None  # null for messages persisted before this column
    created_at: str

    model_config = {"from_attributes": True}
