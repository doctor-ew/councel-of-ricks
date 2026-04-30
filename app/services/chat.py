"""Chat service - orchestrates agents and arbiter."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.arbiter import ArbiterEngine
from app.agents.defense_cross import DefenseCrossAgent
from app.agents.plaintiff_coach import PlaintiffCoachAgent
from app.db.models import FactLedger, Message, Session
from app.schemas.chat import ChatResponse
from app.schemas.profiles import ProfileContext
from app.services.profiles import get_profile_context
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)


class ChatService:
    """Orchestrates chat between witness, agents, and arbiter."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.retrieval = RetrievalService(db)
        self.arbiter = ArbiterEngine(db, self.retrieval)

    async def process_message(
        self,
        session_id: UUID,
        witness_message: str,
        agent_mode: str,
        profile_id: UUID | None = None,
    ) -> ChatResponse:
        """
        Process a witness message and generate agent response.

        Flow:
        1. Store witness message
        2. Arbiter analyzes response (extract facts, check contradictions)
        3. Agent generates follow-up question
        4. Store agent message and new facts
        5. Return response with citations and flags
        """
        # 1. Store witness message
        witness_msg = Message(
            session_id=session_id,
            role="witness",
            content=witness_message,
        )
        self.db.add(witness_msg)
        await self.db.flush()

        # 2. Get conversation context
        context = await self._get_conversation_context(session_id)

        # 3. Arbiter analysis
        arbiter_result = await self.arbiter.analyze_response(
            session_id=session_id,
            witness_message=witness_message,
            conversation_context=context,
        )

        # 4. Store new facts in ledger
        new_fact_ids = []
        for fact in arbiter_result.extracted_facts:
            fact_entry = FactLedger(
                session_id=session_id,
                fact_text=fact["fact"],
                confidence=fact["confidence"],
                source_type="witness",
                source_message_id=witness_msg.id,
                citations=fact.get("citations", []),
                contradicts=fact.get("contradicts", []),
            )
            self.db.add(fact_entry)
            await self.db.flush()
            new_fact_ids.append(fact_entry.id)

        # 5. Load profile context if available
        profile_context = None
        if profile_id:
            profile_context = await get_profile_context(self.db, profile_id)

        # 6. Get appropriate agent
        agent = self._get_agent(agent_mode)

        # 7. Generate agent response
        agent_response = await agent.generate_response(
            session_id=session_id,
            conversation_context=context,
            arbiter_flags=arbiter_result.flags,
            suggested_followups=arbiter_result.suggested_followups,
            profile_context=profile_context,
        )

        # 8. Store agent message
        agent_msg = Message(
            session_id=session_id,
            role="agent",
            content=agent_response.message,
            citations=[c.model_dump(mode="json") for c in agent_response.citations],
            arbiter_flags=[f.model_dump(mode="json") for f in arbiter_result.flags],
            truth_score=arbiter_result.truth_score,
        )
        self.db.add(agent_msg)

        # Commit all changes
        await self.db.commit()

        return ChatResponse(
            agent_message=agent_response.message,
            citations=agent_response.citations,
            arbiter_flags=arbiter_result.flags,
            new_facts=new_fact_ids,
            truth_score=arbiter_result.truth_score,
        )

    async def _get_conversation_context(self, session_id: UUID) -> list[dict]:
        """Get recent conversation history."""
        result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(10)
        )
        messages = result.scalars().all()

        # Reverse to get chronological order
        return [
            {"role": msg.role, "content": msg.content}
            for msg in reversed(messages)
        ]

    def _get_agent(self, agent_mode: str):
        """Get the appropriate agent based on mode."""
        if agent_mode == "plaintiff_coach":
            return PlaintiffCoachAgent(self.db, self.retrieval)
        elif agent_mode == "defense_cross":
            return DefenseCrossAgent(self.db, self.retrieval)
        else:
            raise ValueError(f"Unknown agent mode: {agent_mode}")
