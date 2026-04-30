"""Base agent class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.schemas.chat import ArbiterFlag, Citation
from app.schemas.profiles import ProfileContext
from app.services.retrieval import RetrievalService

settings = get_settings()


@dataclass
class AgentResponse:
    """Response from an agent."""

    message: str
    citations: list[Citation]


class BaseDepositionAgent(ABC):
    """Base class for deposition prep agents."""

    def __init__(self, db: AsyncSession, retrieval: RetrievalService):
        self.db = db
        self.retrieval = retrieval
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """The system prompt for this agent."""
        pass

    @property
    @abstractmethod
    def role_name(self) -> str:
        """Display name for this agent's role."""
        pass

    async def generate_response(
        self,
        session_id: UUID,
        conversation_context: list[dict],
        arbiter_flags: list[ArbiterFlag],
        suggested_followups: list[str],
        profile_context: ProfileContext | None = None,
    ) -> AgentResponse:
        """Generate a response based on context and arbiter analysis."""
        if conversation_context:
            last_witness_msg = next(
                (m["content"] for m in reversed(conversation_context) if m["role"] == "witness"),
                "",
            )
            doc_context, citations = await self.retrieval.search_with_citations(
                last_witness_msg, top_k=3
            )
        else:
            doc_context = ""
            citations = []

        system_msg = self._build_system_message(arbiter_flags, profile_context)

        messages = []
        for msg in conversation_context:
            role = "user" if msg["role"] == "witness" else "assistant"
            messages.append({"role": role, "content": msg["content"]})

        context_msg = self._build_context_message(doc_context, arbiter_flags, suggested_followups)
        messages.append({"role": "user", "content": context_msg})

        response = await self.client.messages.create(
            model=self.model,
            system=system_msg,
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )

        agent_message = response.content[0].text

        return AgentResponse(message=agent_message, citations=citations)

    def _build_system_message(
        self, arbiter_flags: list[ArbiterFlag], profile_context: ProfileContext | None = None
    ) -> str:
        """Build the full system message including base prompt, profile, and flags."""
        base = self.system_prompt

        if profile_context:
            base += profile_context.to_prompt()

        if arbiter_flags:
            flags_text = "\n\nARBITER ALERTS (incorporate these into your questioning):\n"
            for flag in arbiter_flags:
                flags_text += f"- [{flag.flag_type.upper()}] {flag.description}\n"
            base += flags_text

        return base

    def _build_context_message(
        self,
        doc_context: str,
        arbiter_flags: list[ArbiterFlag],
        suggested_followups: list[str],
    ) -> str:
        """Build context message for the current turn."""
        parts = []

        if doc_context:
            parts.append(f"RELEVANT DOCUMENTS:\n{doc_context}")

        if suggested_followups:
            parts.append(
                "SUGGESTED FOLLOW-UP AREAS:\n" + "\n".join(f"- {f}" for f in suggested_followups)
            )

        parts.append(
            "\nBased on the witness's last response and the above context, "
            "ask your next question. Stay in character."
        )

        return "\n\n".join(parts)
