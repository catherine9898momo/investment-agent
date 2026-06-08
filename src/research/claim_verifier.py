"""Verify candidate LLM claims before evidence binding."""

from __future__ import annotations

import re

from src.research.models import ClaimVerificationIssue, ClaimVerificationResult, ResearchRunState
from src.research.synthesizer import CandidateClaim, SynthesisResult

_DIRECT_ADVICE_PATTERNS = [
    r"(建议|应该|可以|适合|立刻|现在)\s*(买入|卖出|加仓|减仓|清仓|满仓|重仓|做空|持有)",
    r"(买入|卖出|加仓|减仓|清仓|满仓|重仓|做空|持有)\s*(吧|即可|就行|是更好选择)",
    r"\b(you should|should|recommend|recommendation:|do)\s+(buy|sell|add|trim|liquidate|short|hold)\b",
    r"\b(buy|sell|add|trim|liquidate|short|hold)\s+(now|immediately|this stock|the stock)\b",
]
_CAUSAL_TERMS = ("因为", "原因", "导致", "归因", "due to", "because", "caused by", "driven by")
_ASSERTIVE_CLAIM_TYPES = {"supporting_factor", "fact_summary", "fit_assessment"}


def verify_synthesis_claims(run: ResearchRunState, synthesis: SynthesisResult) -> ClaimVerificationResult:
    """/**
     * Verify candidate claims before turning them into report claims.
     *
     * @remarks This minimal verifier does not fetch new evidence. Unsupported claims are blocked and,
     * when useful, marked as retrieval_needed for a future retrieval loop.
     */
    """

    fact_types_by_id = _context_fact_types_by_id(run)
    quality_by_id = _context_quality_by_id(run)
    sourceful_fact_ids = {fact.id for fact in run.facts if fact.source_ids}
    allowed_fact_ids = set(fact_types_by_id) or sourceful_fact_ids
    missing_types = {item.fact_type for item in run.missing_facts}
    issues: list[ClaimVerificationIssue] = []
    accepted_indexes: list[int] = []

    for index, claim in enumerate(synthesis.claims):
        claim_issues = _verify_single_claim(claim, allowed_fact_ids, fact_types_by_id, quality_by_id, missing_types)
        issues.extend(claim_issues)
        if not any(issue.severity == "error" for issue in claim_issues):
            accepted_indexes.append(index)

    return ClaimVerificationResult(
        passed=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        accepted_claim_indexes=accepted_indexes,
    )


def filter_synthesis_to_verified_claims(synthesis: SynthesisResult, verification: ClaimVerificationResult) -> SynthesisResult:
    """/** Return a synthesis result containing only claims without verifier errors. */"""

    accepted = set(verification.accepted_claim_indexes)
    return SynthesisResult(
        claims=[claim for index, claim in enumerate(synthesis.claims) if index in accepted],
        human_confirmation_points=synthesis.human_confirmation_points,
        raw_model_output=synthesis.raw_model_output,
    )


def _verify_single_claim(
    claim: CandidateClaim,
    allowed_fact_ids: set[str],
    fact_types_by_id: dict[str, str],
    quality_by_id: dict[str, tuple[str, str]],
    missing_types: set[str],
) -> list[ClaimVerificationIssue]:
    issues: list[ClaimVerificationIssue] = []
    unknown_ids = [fact_id for fact_id in claim.fact_ids if fact_id not in allowed_fact_ids]
    if not claim.fact_ids:
        issues.append(
            ClaimVerificationIssue(
                claim_text=claim.text,
                issue_type="missing_evidence",
                message="Candidate claim did not cite any fact_id.",
                severity="error",
                retrieval_needed=True,
            )
        )
    if unknown_ids:
        issues.append(
            ClaimVerificationIssue(
                claim_text=claim.text,
                issue_type="unsupported_fact_id",
                message="Candidate claim cited fact_id values that are not present in the research context.",
                severity="error",
                fact_ids=unknown_ids,
                retrieval_needed=True,
            )
        )
    if _contains_direct_advice(claim.text):
        issues.append(
            ClaimVerificationIssue(
                claim_text=claim.text,
                issue_type="direct_trading_advice",
                message="Candidate claim contains direct trading advice language.",
                severity="error",
                fact_ids=claim.fact_ids,
            )
        )
    if claim.claim_type in _ASSERTIVE_CLAIM_TYPES and _mentions_missing_fact_type(claim.text, missing_types):
        issues.append(
            ClaimVerificationIssue(
                claim_text=claim.text,
                issue_type="missing_fact_used_as_support",
                message="Candidate claim appears to use a missing evidence category as support.",
                severity="warning",
                fact_ids=claim.fact_ids,
                retrieval_needed=True,
            )
        )
    referenced_types = {fact_types_by_id.get(fact_id) for fact_id in claim.fact_ids if fact_id in fact_types_by_id}
    if _has_causal_language(claim.text) and referenced_types == {"price_move"}:
        issues.append(
            ClaimVerificationIssue(
                claim_text=claim.text,
                issue_type="price_only_causal_inference",
                message="Candidate claim infers cause using only price movement evidence.",
                severity="warning",
                fact_ids=claim.fact_ids,
                retrieval_needed=True,
            )
        )
    weak_ids = [
        fact_id
        for fact_id in claim.fact_ids
        if quality_by_id.get(fact_id, ("medium", "verified")) in {("low", "verified"), ("low", "partial"), ("medium", "partial"), ("high", "partial")}
    ]
    if weak_ids and claim.claim_type in _ASSERTIVE_CLAIM_TYPES:
        issues.append(
            ClaimVerificationIssue(
                claim_text=claim.text,
                issue_type="low_confidence_overstated",
                message="Candidate claim uses partial or low-confidence evidence in an assertive claim type.",
                severity="warning",
                fact_ids=weak_ids,
                retrieval_needed=True,
            )
        )
    return issues


def _context_fact_types_by_id(run: ResearchRunState) -> dict[str, str]:
    if run.research_context:
        return {fact.fact_id: fact.fact_type for fact in run.research_context.facts}
    return {fact.raw_fact_id or fact.id: fact.fact_type for fact in run.verified_facts}


def _context_quality_by_id(run: ResearchRunState) -> dict[str, tuple[str, str]]:
    if run.research_context:
        return {fact.fact_id: (fact.confidence, fact.verification_status) for fact in run.research_context.facts}
    return {fact.raw_fact_id or fact.id: (fact.confidence, fact.verification_status) for fact in run.verified_facts}


def _contains_direct_advice(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in _DIRECT_ADVICE_PATTERNS)


def _has_causal_language(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in _CAUSAL_TERMS)


def _mentions_missing_fact_type(text: str, missing_types: set[str]) -> bool:
    lower = text.lower()
    return any(fact_type.lower() in lower for fact_type in missing_types)
