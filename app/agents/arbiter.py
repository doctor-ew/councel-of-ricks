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
        *,
        truth_score: int = 100,
    ):
        self.extracted_facts = extracted_facts
        self.flags = flags
        self.suggested_followups = suggested_followups
        self.truth_score = truth_score


def _compute_truth_score(facts: list[dict], flags: list[ArbiterFlag]) -> int:
    """
    Deterministically compute a 0-100 truth score from arbiter outputs.

    Penalty table (locked for v1; may be tuned in a follow-up ticket):
      - contradiction flag: -15
      - unsupported flag:   -8
      - fact confidence dont_recall: -5
      - fact confidence uncertain:   -3
      - fact confidence estimate:    -3
      - fact confidence certain:     0

    `vague` flags are intentionally not penalized (vagueness is captured
    via the `uncertain` / `estimate` fact confidence). The `risk` flag is
    not emitted by the current arbiter and is not penalized.
    """
    score = 100
    for f in flags:
        if f.flag_type == "contradiction":
            score -= 15
        elif f.flag_type == "unsupported":
            score -= 8
    for fact in facts:
        c = fact.get("confidence")
        if c == "dont_recall":
            score -= 5
        elif c in ("uncertain", "estimate"):
            score -= 3
    return max(0, min(100, score))


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
        # Step 1: Extract factual claims (also detects inappropriate content in same call)
        extracted_facts, inappropriate = await self._extract_facts(witness_message, conversation_context)
        logger.info(f"Extracted {len(extracted_facts)} facts (inappropriate={inappropriate})")

        # Short-circuit: skip full analysis if content is out of bounds
        if inappropriate:
            flags = [ArbiterFlag(
                flag_type="inappropriate",
                description="ORDER. The witness's response falls outside the scope of legal testimony. Redirect to the question.",
                related_fact_ids=[],
            )]
            return ArbiterAnalysis(
                extracted_facts=[],
                flags=flags,
                suggested_followups=["Redirect — the witness went off-script. Restate the last substantive question."],
                truth_score=0,
            )

        try:
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

            # Step 7: Compute deterministic truth score from facts + flags
            truth_score = _compute_truth_score(supported_facts, flags)

        except Exception:
            logger.exception("Arbiter pipeline failed — returning degraded analysis")
            return ArbiterAnalysis(
                extracted_facts=extracted_facts,
                flags=[],
                suggested_followups=[],
                truth_score=100,
            )

        return ArbiterAnalysis(
            extracted_facts=supported_facts,
            flags=flags,
            suggested_followups=suggested_followups,
            truth_score=truth_score,
        )

    async def _extract_facts(
        self, witness_message: str, context: list[dict]
    ) -> tuple[list[dict], bool]:
        """Use LLM to extract atomic factual claims and detect inappropriate content."""
        recent_context = context[-4:] if context else []
        context_str = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in recent_context
        )

        prompt = f"""You are analyzing a witness response in a legal deposition training simulation.

CONVERSATION CONTEXT:
{context_str}

WITNESS RESPONSE:
{witness_message}

Return a JSON object with two keys:

1. "inappropriate": true if the response contains explicit sexual content, graphic violence, or content clearly intended to derail the simulation rather than participate in it (crude jokes that go beyond R&M humor, harassment, slurs). false otherwise. Rick and Morty-style irreverence and sarcasm are NOT inappropriate.

2. "facts": an array of factual claims extracted from the response. Each element has:
   - "fact": the atomic factual claim
   - "confidence": one of "certain", "uncertain", "estimate", "dont_recall"

If inappropriate is true, facts may be empty. If no facts exist, return an empty array.

Return ONLY the JSON object, no other text. Example:
{{"inappropriate": false, "facts": [{{"fact": "The contract was signed on March 15th", "confidence": "certain"}}]}}"""

        response = await self.client.messages.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=1000,
        )

        try:
            content = response.content[0].text.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                content = content.rsplit("```", 1)[0]
            parsed = json.loads(content)
            return parsed.get("facts", []), bool(parsed.get("inappropriate", False))
        except (json.JSONDecodeError, AttributeError):
            logger.error(f"Failed to parse facts: {response.content[0].text}")
            return [], False

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
                            "explanation", "Oh geez — this seems to contradict what the witness said earlier"
                        ),
                        related_fact_ids=[],
                    )
                )

        # Flag unsupported claims — merge into one flag to avoid repetition
        unsupported = [f for f in facts if not f.get("citations")]
        if len(unsupported) == 1:
            flags.append(
                ArbiterFlag(
                    flag_type="unsupported",
                    description=f"Oh jeez — no docs back this up: \"{unsupported[0]['fact'][:80]}\"",
                    related_fact_ids=[],
                )
            )
        elif len(unsupported) > 1:
            flags.append(
                ArbiterFlag(
                    flag_type="unsupported",
                    description=f"Oh jeez — {len(unsupported)} claims have zero documentary support in the archive",
                    related_fact_ids=[],
                )
            )

        # Flag vague statements
        for fact in facts:
            if fact.get("confidence") in ("uncertain", "estimate"):
                flags.append(
                    ArbiterFlag(
                        flag_type="vague",
                        description=f"Um, this is pretty imprecise and I think someone's going to push on it: {fact['fact'][:100]}...",
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
            if flag.flag_type == "inappropriate":
                followups.append("Redirect — the witness went off-script. Restate the last substantive question.")
            elif flag.flag_type == "contradiction":
                followups.append("Oh geez, you should really clarify that contradiction — it's gonna come up")
            elif flag.flag_type == "unsupported":
                followups.append("Ask them if there's any actual documentation for that claim, please")
            elif flag.flag_type == "vague":
                followups.append("Pin down the specifics — dates, amounts, names — I can't stress this enough")

        return followups[:3]  # Limit to top 3
