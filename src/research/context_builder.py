"""Build evidence-constrained context for research synthesis."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from src.research.models import ContextFact, ContextMissingFact, ResearchContext, ResearchRunState, VerifiedFact


_UNSUPPORTED_CLAIM_CONSTRAINTS = [
    "Use only facts listed in context.facts as support for factual claims.",
    "Do not infer causes from price movement alone; unsupported attribution must be stated as missing evidence.",
    "Do not recommend buying, selling, adding, trimming, holding, shorting, or clearing a position.",
    "Treat partial, stale, missing, failure, unknown, and conflicting facts as uncertainty or risk, not as positive support.",
    "Every generated claim must reference one or more fact_id values from context.facts.",
]


def build_research_context(run: ResearchRunState) -> ResearchContext:
    """/**
     * Convert a full ResearchRunState into the minimal context allowed for synthesis.
     *
     * @param run - Run state after normalization and verified/missing fact table construction.
     * @returns Evidence-constrained context with verified facts, missing facts, and guardrail constraints.
     *
     * @remarks This is the P1 boundary between deterministic retrieval/verification and LLM synthesis.
     */
    """

    facts = [_context_fact_from_verified_fact(item) for item in run.verified_facts if item.source_ids]
    missing_facts = [
        ContextMissingFact(
            fact_type=item.fact_type,
            reason=item.reason,
            required=item.required,
        )
        for item in run.missing_facts
    ]
    source_ids = sorted({source_id for fact in facts for source_id in fact.source_ids})
    user_preferences = [fact for fact in facts if fact.fact_type == "user_preferences"]
    return ResearchContext(
        user_query=run.user_query,
        entity=run.resolved_entity,
        intent_route=run.intent_route,
        time_window=run.time_window,
        attribution_plan=run.attribution_plan,
        facts=facts,
        missing_facts=missing_facts,
        source_ids=source_ids,
        user_preferences=user_preferences,
        unsupported_claim_constraints=list(_UNSUPPORTED_CLAIM_CONSTRAINTS),
    )


def research_context_to_prompt_payload(context: ResearchContext) -> dict[str, Any]:
    """/** Return a JSON-serializable payload for LLM prompts and trace events. */"""

    return asdict(context)


def _context_fact_from_verified_fact(fact: VerifiedFact) -> ContextFact:
    return ContextFact(
        fact_id=fact.raw_fact_id or fact.id,
        fact_type=fact.fact_type,
        text=fact.text,
        source_ids=fact.source_ids,
        observed_at=fact.observed_at,
        confidence=fact.confidence,
        verification_status=fact.verification_status,
        value=fact.value,
    )
