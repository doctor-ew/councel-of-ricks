"""Service for generating batch deposition questions."""

import json
import logging
from uuid import UUID

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import FactLedger, Message, Session
from app.schemas.questions import GeneratedQuestion, QuestionGenerateRequest
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)
settings = get_settings()


class QuestionGenerator:
    """Generates deposition preparation questions based on case context."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model
        self.retrieval = RetrievalService(db)

    async def generate_questions(
        self,
        session_id: UUID,
        request: QuestionGenerateRequest,
    ) -> list[GeneratedQuestion]:
        """Generate batch questions for deposition prep."""
        # Get session context
        session = await self._get_session(session_id)
        if not session:
            raise ValueError("Session not found")

        # Get conversation history for context
        conversation_context = await self._get_conversation_context(session_id)

        # Get established facts
        facts = await self._get_facts(session_id)

        # Get relevant documents based on focus area
        doc_context = ""
        citations = []
        if request.focus_area:
            doc_context, citations = await self.retrieval.search_with_citations(
                request.focus_area, top_k=5
            )
        else:
            # Get general case documents
            doc_context, citations = await self.retrieval.search_with_citations(
                f"deposition {session.witness_name} case facts", top_k=5
            )

        # Build the generation prompt
        prompt = self._build_generation_prompt(
            session=session,
            conversation_context=conversation_context,
            facts=facts,
            doc_context=doc_context,
            request=request,
        )

        # Call Anthropic to generate questions
        response = await self.client.messages.create(
            model=self.model,
            system=self._get_system_prompt(request.difficulty),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=3000,
        )

        # Parse response
        result = json.loads(response.content[0].text)
        questions = result.get("questions", [])

        # Convert to GeneratedQuestion objects
        generated = []
        for q in questions[: request.count]:
            generated.append(
                GeneratedQuestion(
                    question=q.get("question", ""),
                    purpose=q.get("purpose", ""),
                    suggested_followups=q.get("followups", [])[:3],
                    citations=[c.model_dump(mode="json") for c in citations[:2]] if request.include_citations else [],
                    topic=q.get("topic", "general"),
                )
            )

        return generated

    def _get_system_prompt(self, difficulty: str) -> str:
        """Get system prompt based on difficulty level."""
        base = """You are an expert litigation attorney generating deposition questions.
Your questions should be strategically designed to:
- Establish key facts
- Test witness credibility
- Identify inconsistencies
- Build the case narrative

Always respond with valid JSON in this format:
{
  "questions": [
    {
      "question": "The actual question to ask",
      "purpose": "Why this question matters strategically",
      "followups": ["Follow-up 1", "Follow-up 2"],
      "topic": "Category like timeline, damages, credibility, etc."
    }
  ]
}
"""
        if difficulty == "aggressive":
            base += """
AGGRESSIVE MODE: Generate challenging cross-examination style questions that:
- Challenge the witness's version of events
- Highlight contradictions and inconsistencies
- Use leading questions strategically
- Press on weak points in testimony
"""
        elif difficulty == "expert":
            base += """
EXPERT MODE: Generate sophisticated questions that:
- Require detailed technical knowledge to answer
- Probe complex contractual or legal issues
- Test the limits of the witness's expertise
- Set up impeachment opportunities
"""
        else:
            base += """
STANDARD MODE: Generate balanced preparation questions that:
- Cover key facts systematically
- Are clear and direct
- Help establish the witness's narrative
- Identify areas needing more preparation
"""
        return base

    def _build_generation_prompt(
        self,
        session: Session,
        conversation_context: list[dict],
        facts: list[dict],
        doc_context: str,
        request: QuestionGenerateRequest,
    ) -> str:
        """Build the prompt for question generation."""
        parts = [
            f"Generate {request.count} deposition questions for witness: {session.witness_name}",
            f"Session mode: {session.agent_mode}",
        ]

        if request.focus_area:
            parts.append(f"\nFOCUS AREA: {request.focus_area}")
            parts.append("Concentrate questions on this specific topic.")

        if facts:
            parts.append("\nESTABLISHED FACTS FROM SESSION:")
            for f in facts[:10]:
                confidence = f.get("confidence", "unknown")
                parts.append(f"- [{confidence}] {f.get('fact_text', '')[:200]}")

        if conversation_context:
            parts.append("\nRECENT CONVERSATION CONTEXT:")
            for msg in conversation_context[-6:]:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")[:300]
                parts.append(f"[{role}]: {content}")

        if doc_context:
            parts.append("\nRELEVANT CASE DOCUMENTS:")
            parts.append(doc_context[:2000])

        parts.append(f"\nGenerate exactly {request.count} questions in JSON format.")

        return "\n".join(parts)

    async def _get_session(self, session_id: UUID) -> Session | None:
        """Get session by ID."""
        result = await self.db.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()

    async def _get_conversation_context(self, session_id: UUID) -> list[dict]:
        """Get recent conversation history."""
        result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(10)
        )
        messages = result.scalars().all()
        return [{"role": msg.role, "content": msg.content} for msg in reversed(messages)]

    async def _get_facts(self, session_id: UUID) -> list[dict]:
        """Get established facts from session."""
        result = await self.db.execute(
            select(FactLedger)
            .where(FactLedger.session_id == session_id)
            .where(FactLedger.superseded_by.is_(None))
            .order_by(FactLedger.created_at.desc())
            .limit(15)
        )
        facts = result.scalars().all()
        return [
            {"fact_text": f.fact_text, "confidence": f.confidence, "citations": f.citations}
            for f in facts
        ]


def format_questions_markdown(
    questions: list[GeneratedQuestion],
    include_citations: bool = True,
    include_followups: bool = True,
    include_purpose: bool = False,
) -> str:
    """Format questions as markdown for export."""
    lines = ["# Deposition Preparation Questions\n"]

    for i, q in enumerate(questions, 1):
        lines.append(f"## Question {i}: {q.topic.title()}\n")
        lines.append(f"**{q.question}**\n")

        if include_purpose and q.purpose:
            lines.append(f"*Purpose: {q.purpose}*\n")

        if include_followups and q.suggested_followups:
            lines.append("\n**Suggested Follow-ups:**")
            for fu in q.suggested_followups:
                lines.append(f"- {fu}")
            lines.append("")

        if include_citations and q.citations:
            lines.append("\n**Document References:**")
            for c in q.citations:
                doc_name = c.get("document_name", "Unknown")
                page = c.get("page_number", "?")
                lines.append(f"- {doc_name}, p. {page}")
            lines.append("")

        lines.append("---\n")

    return "\n".join(lines)


def format_questions_text(
    questions: list[GeneratedQuestion],
    include_citations: bool = True,
    include_followups: bool = True,
) -> str:
    """Format questions as plain text for export."""
    lines = ["DEPOSITION PREPARATION QUESTIONS", "=" * 40, ""]

    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. [{q.topic.upper()}]")
        lines.append(f"   {q.question}")

        if include_followups and q.suggested_followups:
            lines.append("   Follow-ups:")
            for fu in q.suggested_followups:
                lines.append(f"     - {fu}")

        if include_citations and q.citations:
            lines.append("   Sources:")
            for c in q.citations:
                doc_name = c.get("document_name", "Unknown")
                page = c.get("page_number", "?")
                lines.append(f"     - {doc_name}, p. {page}")

        lines.append("")

    return "\n".join(lines)
