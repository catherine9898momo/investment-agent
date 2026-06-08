"""Plan retrieval tasks from claim verifier issues."""

from __future__ import annotations

from src.research.models import (
    ClaimVerificationIssue,
    ClaimVerificationResult,
    MissingFact,
    ResearchRunState,
    RetrievalNeedPlan,
    RetrievalTask,
)

_PRICE_CAUSAL_FACT_TYPES = ("sector_move", "peer_moves", "news_events")
_DEFAULT_INDEX_SYMBOLS = ["QQQ", "SMH", "SOXX"]

_FACT_TYPE_TOOL_HINTS = {
    "price_move": ["finance.get_price_history"],
    "sector_move": ["finance.get_price_history"],
    "peer_moves": ["finance.get_price_history"],
    "news_events": ["news.search"],
    "corporate_actions": ["corporate_actions.lookup"],
    "earnings_or_guidance": ["company_filings.search", "news.search"],
    "analyst_actions": ["news.search"],
    "macro_context": ["finance.get_price_history", "news.search"],
}

_FACT_TYPE_SOURCE_REQUIREMENTS = {
    "price_move": ["market data provider with timestamps"],
    "sector_move": ["market data provider with timestamps"],
    "peer_moves": ["market data provider with timestamps"],
    "news_events": ["company press release, SEC filing, or reputable financial news"],
    "corporate_actions": ["exchange, company investor relations, or corporate actions provider"],
    "earnings_or_guidance": ["company investor relations, SEC filing, or earnings transcript"],
    "analyst_actions": ["reputable financial news or analyst action feed"],
    "macro_context": ["market data provider or official macro data source"],
}


def build_retrieval_need_plan(
    run: ResearchRunState,
    verification: ClaimVerificationResult | None = None,
) -> RetrievalNeedPlan:
    """/**
     * Convert retrieval_needed verifier issues into structured retrieval tasks.
     *
     * @remarks The planner is intentionally non-networked. It produces an executor-ready
     * task list without fetching sources or mutating verified facts.
     */
    """

    verification = verification or run.claim_verification
    retrieval_issues = [issue for issue in (verification.issues if verification else []) if issue.retrieval_needed]
    tasks: list[RetrievalTask] = []
    for issue in retrieval_issues:
        tasks.extend(_tasks_for_issue(run, issue))

    plan = RetrievalNeedPlan(
        user_query=run.user_query,
        tasks=_dedupe_tasks(tasks),
        issue_count=len(retrieval_issues),
    )
    run.retrieval_need_plan = plan
    return plan


def _tasks_for_issue(run: ResearchRunState, issue: ClaimVerificationIssue) -> list[RetrievalTask]:
    if issue.issue_type == "price_only_causal_inference":
        return [_task_for_fact_type(run, issue, fact_type, "high") for fact_type in _PRICE_CAUSAL_FACT_TYPES]
    if issue.issue_type == "missing_fact_used_as_support":
        missing_facts = _matching_missing_facts(run, issue)
        return [_task_for_missing_fact(run, issue, missing, "high") for missing in missing_facts]
    if issue.issue_type == "low_confidence_overstated":
        fact_types = _fact_types_for_ids(run, issue.fact_ids) or ["supporting_fact"]
        return [_task_for_fact_type(run, issue, fact_type, "medium", fact_ids=issue.fact_ids) for fact_type in fact_types]
    if issue.issue_type == "unsupported_fact_id":
        return [_unsupported_fact_task(run, issue, fact_id) for fact_id in issue.fact_ids or [""]]
    if issue.issue_type == "missing_evidence":
        return [_task_for_fact_type(run, issue, "supporting_fact", "high")]
    return []


def _task_for_missing_fact(
    run: ResearchRunState,
    issue: ClaimVerificationIssue,
    missing: MissingFact,
    priority: str,
) -> RetrievalTask:
    task = _task_for_fact_type(run, issue, missing.fact_type, priority, fact_ids=issue.fact_ids)
    task.reason = missing.reason
    return task


def _task_for_fact_type(
    run: ResearchRunState,
    issue: ClaimVerificationIssue,
    fact_type: str,
    priority: str,
    fact_ids: list[str] | None = None,
) -> RetrievalTask:
    return RetrievalTask(
        fact_type=fact_type,
        issue_type=issue.issue_type,
        query_focus=_query_focus(run, fact_type),
        priority=priority,
        reason=_reason_for_fact_type(fact_type, issue),
        candidate_tools=list(_FACT_TYPE_TOOL_HINTS.get(fact_type, ["reliable_source.search"])),
        source_requirements=list(_FACT_TYPE_SOURCE_REQUIREMENTS.get(fact_type, ["official or reputable source"])),
        symbols=_symbols_for_fact_type(run, fact_type),
        fact_ids=list(fact_ids or []),
        claim_text=issue.claim_text,
    )


def _unsupported_fact_task(run: ResearchRunState, issue: ClaimVerificationIssue, fact_id: str) -> RetrievalTask:
    fact_type = _infer_fact_type_from_id(fact_id)
    task = _task_for_fact_type(run, issue, fact_type, "high", fact_ids=[fact_id] if fact_id else [])
    task.query_focus = f"Find reliable support for unsupported fact_id {fact_id!r}: {issue.claim_text}"
    task.source_requirements = ["official source when available", "reputable financial news or data provider"]
    return task


def _matching_missing_facts(run: ResearchRunState, issue: ClaimVerificationIssue) -> list[MissingFact]:
    claim_lower = issue.claim_text.lower()
    matched = [missing for missing in run.missing_facts if missing.fact_type.lower() in claim_lower]
    if matched:
        return matched
    return [missing for missing in run.missing_facts if missing.required]


def _fact_types_for_ids(run: ResearchRunState, fact_ids: list[str]) -> list[str]:
    by_id: dict[str, str] = {}
    if run.research_context:
        by_id.update({fact.fact_id: fact.fact_type for fact in run.research_context.facts})
    by_id.update({fact.raw_fact_id or fact.id: fact.fact_type for fact in run.verified_facts})
    return sorted({by_id[fact_id] for fact_id in fact_ids if fact_id in by_id})


def _symbols_for_fact_type(run: ResearchRunState, fact_type: str) -> list[str]:
    entity_symbol = run.resolved_entity.symbol if run.resolved_entity else None
    if fact_type == "sector_move":
        if run.attribution_plan and run.attribution_plan.index_symbols:
            return list(run.attribution_plan.index_symbols)
        return list(_DEFAULT_INDEX_SYMBOLS)
    if fact_type == "peer_moves":
        return list(run.attribution_plan.peer_symbols if run.attribution_plan else [])
    if fact_type in {"price_move", "news_events", "earnings_or_guidance", "corporate_actions", "analyst_actions", "supporting_fact"}:
        return [entity_symbol] if entity_symbol else []
    if fact_type == "macro_context":
        return ["QQQ"]
    return [entity_symbol] if entity_symbol else []


def _query_focus(run: ResearchRunState, fact_type: str) -> str:
    window = f" from {run.time_window.start_date} to {run.time_window.end_date}" if run.time_window else " for the relevant window"
    symbol = run.resolved_entity.symbol if run.resolved_entity else "the target company"
    if fact_type == "sector_move":
        return f"Compare sector or ETF moves{window} against {symbol}."
    if fact_type == "peer_moves":
        return f"Compare peer stock moves{window} against {symbol}."
    if fact_type == "news_events":
        return f"Find company-specific news events for {symbol}{window}."
    if fact_type == "earnings_or_guidance":
        return f"Find earnings, guidance, or management commentary for {symbol}{window}."
    if fact_type == "corporate_actions":
        return f"Check corporate actions for {symbol}{window}."
    if fact_type == "price_move":
        return f"Verify price movement for {symbol}{window}."
    return f"Find reliable evidence for {fact_type}{window}."


def _reason_for_fact_type(fact_type: str, issue: ClaimVerificationIssue) -> str:
    if issue.issue_type == "price_only_causal_inference":
        return f"Causal attribution needs {fact_type} evidence, not price movement alone."
    if issue.issue_type == "low_confidence_overstated":
        return f"Assertive claim needs higher-confidence {fact_type} evidence."
    if issue.issue_type == "missing_evidence":
        return "Claim cited no supporting fact_id and needs traceable evidence before use."
    return issue.message


def _infer_fact_type_from_id(fact_id: str) -> str:
    lower = fact_id.lower()
    if any(term in lower for term in ("guidance", "earnings", "eps", "revenue")):
        return "earnings_or_guidance"
    if any(term in lower for term in ("sector", "smh", "soxx", "qqq")):
        return "sector_move"
    if any(term in lower for term in ("peer", "competitor")):
        return "peer_moves"
    if any(term in lower for term in ("news", "event")):
        return "news_events"
    if any(term in lower for term in ("corporate", "split", "dividend")):
        return "corporate_actions"
    if any(term in lower for term in ("price", "quote", "move")):
        return "price_move"
    return "supporting_fact"


def _dedupe_tasks(tasks: list[RetrievalTask]) -> list[RetrievalTask]:
    seen: set[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = set()
    deduped: list[RetrievalTask] = []
    for task in tasks:
        key = (task.issue_type, task.fact_type, tuple(task.symbols), tuple(task.fact_ids))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(task)
    return deduped
