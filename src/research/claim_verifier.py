"""Verify candidate LLM claims before evidence binding."""

from __future__ import annotations

import re
from typing import Any

from src.research.models import ClaimVerificationIssue, ClaimVerificationResult, ResearchRunState
from src.research.synthesizer import CandidateClaim, SynthesisResult
from src.research.trace import TraceLogger

_DIRECT_ADVICE_PATTERNS = [
    r"(建议|应该|可以|适合|立刻|现在)\s*(买入|卖出|加仓|减仓|清仓|满仓|重仓|做空|持有)",
    r"(买入|卖出|加仓|减仓|清仓|满仓|重仓|做空|持有)\s*(吧|即可|就行|是更好选择)",
    r"\b(you should|should|recommend|recommendation:|do)\s+(buy|sell|add|trim|liquidate|short|hold)\b",
    r"\b(buy|sell|add|trim|liquidate|short|hold)\s+(now|immediately|this stock|the stock)\b",
]
_CAUSAL_TERMS = ("因为", "原因", "导致", "归因", "due to", "because", "caused by", "driven by")
_ASSERTIVE_CLAIM_TYPES = {"supporting_factor", "fact_summary", "fit_assessment"}
_MODULE_TAG = "src.research.claim_verifier"


def verify_synthesis_claims(run: ResearchRunState, synthesis: SynthesisResult, trace: TraceLogger | None = None) -> ClaimVerificationResult:
    """/**
     * Verify candidate claims before turning them into report claims.
     *
     * @param run - 当前研究 run，提供可引用 facts、verified facts、missing facts 和 research context。
     * @param synthesis - LLM 或 mock synthesizer 生成的候选 claims。
     * @param trace - 可选 trace logger；传入时会记录完整函数输入、输出和模块函数 tag。
     * @returns ClaimVerificationResult，包含通过状态、issue 列表和可保留 claim index。
     *
     * @remarks This verifier does not fetch new evidence. Unsupported claims are blocked and,
     * when useful, marked as retrieval_needed for a future retrieval loop.
     */
    """

    fact_types_by_id = _context_fact_types_by_id(run)
    _trace_io(
        trace,
        "_context_fact_types_by_id",
        {"run_id": run.run_id, "has_research_context": run.research_context is not None},
        fact_types_by_id,
    )

    quality_by_id = _context_quality_by_id(run)
    _trace_io(
        trace,
        "_context_quality_by_id",
        {"run_id": run.run_id, "has_research_context": run.research_context is not None},
        quality_by_id,
    )

    sourceful_fact_ids = {fact.id for fact in run.facts if fact.source_ids}
    allowed_fact_ids = set(fact_types_by_id) or sourceful_fact_ids
    missing_types = {item.fact_type for item in run.missing_facts}
    issues: list[ClaimVerificationIssue] = []
    accepted_indexes: list[int] = []

    for index, claim in enumerate(synthesis.claims):
        claim_issues = _verify_single_claim(claim, allowed_fact_ids, fact_types_by_id, quality_by_id, missing_types, trace, index)
        issues.extend(claim_issues)
        if not any(issue.severity == "error" for issue in claim_issues):
            accepted_indexes.append(index)

    result = ClaimVerificationResult(
        passed=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        accepted_claim_indexes=accepted_indexes,
    )
    _trace_io(
        trace,
        "verify_synthesis_claims",
        {
            "run_id": run.run_id,
            "user_query": run.user_query,
            "claims": synthesis.claims,
            "allowed_fact_ids": sorted(allowed_fact_ids),
            "missing_types": sorted(missing_types),
        },
        result,
    )
    return result


def filter_synthesis_to_verified_claims(
    synthesis: SynthesisResult,
    verification: ClaimVerificationResult,
    trace: TraceLogger | None = None,
) -> SynthesisResult:
    """/**
     * Return a synthesis result containing only claims without verifier errors.
     *
     * @param synthesis - 原始候选 claims。
     * @param verification - claim verifier 输出的核验结果。
     * @param trace - 可选 trace logger；传入时记录过滤前后的完整 claims。
     */
    """

    accepted = set(verification.accepted_claim_indexes)
    result = SynthesisResult(
        claims=[claim for index, claim in enumerate(synthesis.claims) if index in accepted],
        human_confirmation_points=synthesis.human_confirmation_points,
        raw_model_output=synthesis.raw_model_output,
    )
    _trace_io(
        trace,
        "filter_synthesis_to_verified_claims",
        {"synthesis": synthesis, "verification": verification},
        result,
    )
    return result


def _verify_single_claim(
    claim: CandidateClaim,
    allowed_fact_ids: set[str],
    fact_types_by_id: dict[str, str],
    quality_by_id: dict[str, tuple[str, str]],
    missing_types: set[str],
    trace: TraceLogger | None = None,
    claim_index: int | None = None,
) -> list[ClaimVerificationIssue]:
    """/**
     * 核验单条 CandidateClaim 的 provenance 和基础安全边界。
     *
     * @param claim - 待验证的候选结论。
     * @param allowed_fact_ids - 当前 context 允许引用的 fact_id 集合。
     * @param fact_types_by_id - fact_id 到 fact_type 的映射。
     * @param quality_by_id - fact_id 到 confidence/status 的映射。
     * @param missing_types - 当前 run 显式暴露的缺失事实类型。
     * @param trace - 可选 trace logger，用于记录完整输入输出。
     * @param claim_index - claim 在 synthesis.claims 中的位置，方便 trace 回放。
     */
    """

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
    _trace_io(
        trace,
        "_verify_single_claim",
        {
            "claim_index": claim_index,
            "claim": claim,
            "allowed_fact_ids": sorted(allowed_fact_ids),
            "fact_types_by_id": fact_types_by_id,
            "quality_by_id": quality_by_id,
            "missing_types": sorted(missing_types),
        },
        issues,
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


def _trace_io(trace: TraceLogger | None, function: str, inputs: Any, output: Any) -> None:
    """/**
     * 写入 claim_verifier 模块内函数的完整输入输出 trace。
     *
     * @param trace - 可选 TraceLogger；为空时保持旧调用方行为不变。
     * @param function - 当前函数名，会和模块名组成 payload.tag。
     * @param inputs - 函数输入，必须保留足够字段用于复盘。
     * @param output - 函数输出，JSON 序列化时不做截断。
     */
    """

    if trace is None:
        return
    trace.append_function_io(_MODULE_TAG, function, inputs, output)
