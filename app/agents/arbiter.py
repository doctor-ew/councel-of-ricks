"""Arbiter Engine - fact extraction and contradiction detection."""

import json
import logging
from uuid import UUID

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import FactLedger
from app.schemas.chat import ArbiterFlag
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)
settings = get_settings()


class ArbiterAnalysis:
    """Result of arbiter analysis."""

    def __init__(
        self,
        extracted_facts: list[dict],
        flags: list[ArbiterFlag],
        suggested_followups: list[str],
    ):
        self.extracted_facts = extracted_facts
        self.flags = flags
        self.suggested_followups = suggested_followups


class ArbiterEngine:
    """
    Neutral oversight engine that:
    1. Extracts factual claims from witness responses
    2. Checks against existing ledger for contradictions
    3. Attempts to find documentary support via RAG
    4. Flags risks and unsupported claims
    """

    def __init__(self, db: AsyncSession, retrieval: RetrievalService):
        self.db = db
        self.retrieval = retrieval
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    async def analyze_response(
        self,
        session_id: UUID,
        witness_message: str,
        conversation_context: list[dict],
    ) -> ArbiterAnalysis:
        """Analyze a witness response for facts, contradictions, and risks."""
        # Step 1: Extract factual claims
        extracted_facts = await self._extract_facts(witness_message, conversation_context)
        logger.info(f"Extracted {len(extracted_facts)} facts from response")

        # Step 2: Get existing facts for contradiction check
        existing_facts = await self._get_existing_facts(session_id)

        # Step 3: Check for contradictions
        contradictions = await self._check_contradictions(extracted_facts, existing_facts)

        # Step 4: Find documentary support for each fact
        supported_facts = await self._find_support(extracted_facts)

        # Step 5: Generate flags
        flags = self._generate_flags(supported_facts, contradictions)

        # Step 6: Suggest follow-ups
        suggested_followups = self._suggest_followups(flags, supported_facts)

        return ArbiterAnalysis(
            extracted_facts=supported_facts,
            flags=flags,
            suggested_followups=suggested_followups,
        )

    async def _extract_facts(
        self, witness_message: str, context: list[dict]
    ) -> list[dict]:
        """Use LLM to extract atomic factual claims."""
        # Get recent context
        recent_context = context[-4:] if context else []
        context_str = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in recent_context
        )

        prompt = f"""Extract factual claims from this witness response. For each claim, assess the witness's confidence level.

CONVERSATION CONTEXT:
{context_str}

WITNESS RESPONSE:
{witness_message}

Extract each distinct factual claim. Return a JSON array where each element has:
- "fact": the atomic factual claim (one specific thing)
- "confidence": one of "certain", "uncertain", "estimate", "dont_recall"

Examples of confidence levels:
- "certain": "The contract was signed on March 15th" (specific, definite)
- "uncertain": "I think it was around March" (hedging language)
- "estimate": "It probably cost about $5,000" (approximation)
- "dont_recall": "I don't remember exactly when" (explicit non-memory)

Return ONLY the JSON array, no other text. If no facts, return []."""

        response = await self.client.messages.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=1000,
        )

        try:
            content = response.content[0].text
            # Clean up potential markdown formatting
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                content = content.rsplit("```", 1)[0]
            return json.loads(content)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse facts: {response.content[0].text}")
            return []

    async def _get_existing_facts(self, session_id: UUID) -> list[dict]:
        """Get existing facts from the ledger."""
        result = await self.db.execute(
            select(FactLedger)
            .where(FactLedger.session_id == session_id)
            .where(FactLedger.superseded_by.is_(None))
        )
        facts = result.scalars().all()

        return [
            {
                "id": str(f.id),
                "fact": f.fact_text,
                "confidence": f.confidence,
            }
            for f in facts
        ]

    async def _check_contradictions(
        self, new_facts: list[dict], existing_facts: list[dict]
    ) -> list[dict]:
        """Check if new facts contradict existing ones."""
        if not new_facts or not existing_facts:
            return []

        prompt = f"""Check if any new facts contradict existing facts.

EXISTING FACTS (already established):
{json.dumps(existing_facts, indent=2)}

NEW FACTS (just stated):
{json.dumps(new_facts, indent=2)}

Return a JSON array of contradictions found. Each element should have:
- "new_fact_index": index of the new fact (0-based)
- "existing_fact_id": id of the contradicted existing fact
- "explanation": brief explanation of the contradiction

Only flag clear contradictions, not minor variations. Return [] if no contradictions."""

        response = await self.client.messages.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=500,
        )

        try:
            content = response.content[0].text
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                content = content.rsplit("```", 1)[0]
            return json.loads(content)
        except json.JSONDecodeError:
            return []

    async def _find_support(self, facts: list[dict]) -> list[dict]:
        """Try to find documentary support for each fact."""
        supported_facts = []

        for fact in facts:
            # Search for relevant documents
            results = await self.retrieval.search(fact["fact"], top_k=2)

            citations = []
            if results:
                # Check if results actually support the fact
                for result in results:
                    if result["score"] > 0.7:  # Only include high-relevance matches
                        citations.append({
                            "document_id": str(result["document_id"]),
                            "document_name": result["document_name"],
                            "page_number": result["page_number"],
                            "excerpt": result["content"][:200],
                        })

            supported_facts.append({
                **fact,
                "citations": citations,
                "contradicts": [],
            })

        return supported_facts

    def _generate_flags(
        self, facts: list[dict], contradictions: list[dict]
    ) -> list[ArbiterFlag]:
        """Generate arbiter flags based on analysis."""
        flags = []

        # Flag contradictions
        for contradiction in contradictions:
            idx = contradiction.get("new_fact_index", 0)
            if idx < len(facts):
                flags.append(
                    ArbiterFlag(
                        flag_type="contradiction",
                        description=contradiction.get(
                            "explanation", "Potential contradiction with earlier statement"
                        ),
                        related_fact_ids=[],
                    )
                )

        # Flag unsupported claims
        for fact in facts:
            if not fact.get("citations"):
                flags.append(
                    ArbiterFlag(
                        flag_type="unsupported",
                        description=f"No documentary support found for: {fact['fact'][:100]}...",
                        related_fact_ids=[],
                    )
                )

        # Flag vague statements
        for fact in facts:
            if fact.get("confidence") in ("uncertain", "estimate"):
                flags.append(
                    ArbiterFlag(
                        flag_type="vague",
                        description=f"Imprecise statement: {fact['fact'][:100]}...",
                        related_fact_ids=[],
                    )
                )

        return flags

    def _suggest_followups(
        self, flags: list[ArbiterFlag], facts: list[dict]
    ) -> list[str]:
        """Suggest follow-up questions based on flags."""
        followups = []

        for flag in flags:
            if flag.flag_type == "contradiction":
                followups.append("Clarify the apparent contradiction in testimony")
            elif flag.flag_type == "unsupported":
                followups.append("Ask about documentary evidence for the claim")
            elif flag.flag_type == "vague":
                followups.append("Pin down specifics (dates, amounts, names)")

        return followups[:3]  # Limit to top 3
