"""Clerk Agent - attorney's research assistant for document and fact lookup."""

import logging
from uuid import UUID

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import FactLedger
from app.schemas.chat import Citation
from app.schemas.clerk import ClerkMessage, ClerkResponse, ClerkSource
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)
settings = get_settings()

CLERK_SYSTEM_PROMPT = """You are a legal research clerk assisting an attorney with deposition preparation. Your role is to:

1. Search case documents and answer questions about their contents
2. Reference established facts from witness testimony
3. Find connections between documents and testimony
4. Provide precise, citation-backed answers

IMPORTANT RULES:
- Always cite your sources. Reference specific documents and page numbers.
- If information comes from the fact ledger (witness testimony), note the confidence level.
- If you cannot find relevant information, say so clearly. Do NOT fabricate answers.
- Be concise but thorough. Attorneys need actionable information.
- When referencing documents, use the format: [Document Name, p.X]
- Distinguish between what documents say vs what witnesses have testified
- Flag any contradictions between documents and testimony

You have access to:
- Case documents (contracts, correspondence, invoices, photos, etc.)
- A fact ledger tracking witness testimony with confidence levels
"""


class ClerkService:
    """Attorney's research assistant that searches documents and facts."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.retrieval = RetrievalService(db)
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    async def ask(
        self,
        query: str,
        session_id: UUID | None = None,
        conversation_history: list[ClerkMessage] | None = None,
    ) -> ClerkResponse:
        """
        Process an attorney's research query.

        1. Search case documents via RAG
        2. Search fact ledger for relevant established facts
        3. Synthesize an answer with citations
        """
        # 1. Search documents
        doc_results = await self.retrieval.search(query, top_k=5)
        doc_context, citations = await self.retrieval.search_with_citations(query, top_k=5)

        # 2. Search fact ledger
        facts_context, fact_sources = await self._search_facts(query, session_id)

        # 3. Build sources list
        sources = []
        for result in doc_results:
            sources.append(
                ClerkSource(
                    source_type="document",
                    content=result["content"][:300],
                    document_name=result["document_name"],
                    page_number=result["page_number"],
                    similarity_score=result["score"],
                )
            )
        sources.extend(fact_sources)

        # 4. Build LLM prompt with all context
        messages = []

        # Add conversation history for continuity
        if conversation_history:
            for msg in conversation_history[-6:]:  # Last 6 messages
                role = "user" if msg.role == "user" else "assistant"
                messages.append({"role": role, "content": msg.content})

        # Build the research context
        context_parts = []

        if doc_context:
            context_parts.append(f"CASE DOCUMENTS:\n{doc_context}")

        if facts_context:
            context_parts.append(f"ESTABLISHED FACTS FROM TESTIMONY:\n{facts_context}")

        if not doc_context and not facts_context:
            context_parts.append(
                "NOTE: No relevant documents or facts were found for this query. "
                "Let the attorney know and suggest alternative search terms."
            )

        context_str = "\n\n---\n\n".join(context_parts)

        user_prompt = f"""RESEARCH CONTEXT:
{context_str}

ATTORNEY'S QUESTION:
{query}

Provide a clear, citation-backed answer. Reference specific documents and page numbers."""

        messages.append({"role": "user", "content": user_prompt})

        # 5. Call LLM
        response = await self.client.messages.create(
            model=self.model,
            system=CLERK_SYSTEM_PROMPT,
            messages=messages,
            temperature=0.3,  # Lower temp for factual accuracy
            max_tokens=1500,
        )

        answer = response.content[0].text

        return ClerkResponse(
            answer=answer,
            citations=citations,
            sources=sources,
            facts_referenced=len(fact_sources),
            documents_searched=len(doc_results),
        )

    async def _search_facts(
        self, query: str, session_id: UUID | None = None
    ) -> tuple[str, list[ClerkSource]]:
        """Search the fact ledger for relevant established facts."""
        # Build query for facts
        stmt = (
            select(FactLedger)
            .where(FactLedger.superseded_by.is_(None))
            .order_by(FactLedger.created_at.desc())
            .limit(50)
        )

        if session_id:
            stmt = stmt.where(FactLedger.session_id == session_id)

        result = await self.db.execute(stmt)
        all_facts = result.scalars().all()

        if not all_facts:
            return "", []

        # Use LLM to find relevant facts (more flexible than keyword search)
        facts_text = "\n".join(
            f"[{i}] ({f.confidence}) {f.fact_text}" for i, f in enumerate(all_facts)
        )

        relevance_prompt = f"""Given the query: "{query}"

Which of these established facts are relevant? Return ONLY the index numbers (comma-separated) of relevant facts. If none are relevant, return "NONE".

FACTS:
{facts_text}"""

        response = await self.client.messages.create(
            model=self.model,
            messages=[{"role": "user", "content": relevance_prompt}],
            max_tokens=200,
        )

        relevant_text = response.content[0].text

        if "NONE" in relevant_text.upper():
            return "", []

        # Parse indices
        try:
            indices = [int(x.strip()) for x in relevant_text.split(",") if x.strip().isdigit()]
        except ValueError:
            return "", []

        relevant_facts = [all_facts[i] for i in indices if i < len(all_facts)]

        if not relevant_facts:
            return "", []

        # Format facts as context
        context_parts = []
        sources = []

        for fact in relevant_facts:
            confidence_label = {
                "certain": "CERTAIN",
                "uncertain": "UNCERTAIN",
                "estimate": "ESTIMATE",
                "dont_recall": "WITNESS DOESN'T RECALL",
            }.get(fact.confidence, fact.confidence.upper())

            context_parts.append(
                f"- [{confidence_label}] {fact.fact_text}"
            )

            sources.append(
                ClerkSource(
                    source_type="fact_ledger",
                    content=fact.fact_text,
                    confidence=fact.confidence,
                )
            )

        facts_context = "\n".join(context_parts)
        return facts_context, sources
