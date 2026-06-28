"""Deterministic quality audit for research runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.research.models import ResearchRunState, VerifiedFact


@dataclass(frozen=True)
class QualityIssue:
    issue_type: str
    severity: Literal["info", "warning", "error"]
    message: str
    affected_fact_types: list[str] = field(default_factory=list)
    affected_fact_ids: list[str] = field(default_factory=list)
    retrieval_needed: bool = False
    suggested_task_type: str | None = None


class ReportQualityAuditor:
    """Audit completed research runs without fetching new evidence."""

    def audit(self, run: ResearchRunState, research_depth: str = "normal") -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        fact_types = {fact.fact_type for fact in run.verified_facts}

        if "price_move" not in fact_types:
            issues.append(QualityIssue(
                issue_type="missing_price_move",
                severity="error",
                message="Missing price_move evidence.",
                affected_fact_types=["price_move"],
                retrieval_needed=True,
            ))

        news = _first_fact(run, "news_events")
        if news is None:
            issues.append(QualityIssue(
                issue_type="missing_news_events",
                severity="warning",
                message="Missing news_events evidence.",
                affected_fact_types=["news_events"],
                retrieval_needed=True,
                suggested_task_type="retry_news_zh",
            ))
        elif news.verification_status == "partial" or news.confidence == "low":
            issues.append(QualityIssue(
                issue_type="partial_news_events",
                severity="warning",
                message="News evidence is partial or low confidence.",
                affected_fact_types=["news_events"],
                affected_fact_ids=[news.raw_fact_id or news.id],
                retrieval_needed=True,
                suggested_task_type="retry_news_zh",
            ))

        if _plan_needs(run, "sector_move") and "sector_move" not in fact_types:
            issues.append(QualityIssue(
                issue_type="missing_sector_move",
                severity="warning",
                message="Missing sector/index comparison evidence.",
                affected_fact_types=["sector_move"],
                retrieval_needed=True,
                suggested_task_type="fetch_sector_history",
            ))

        if _plan_needs(run, "peer_moves") and "peer_moves" not in fact_types:
            issues.append(QualityIssue(
                issue_type="missing_peer_moves",
                severity="warning",
                message="Missing peer comparison evidence.",
                affected_fact_types=["peer_moves"],
                retrieval_needed=True,
                suggested_task_type="fetch_peer_history",
            ))

        if research_depth == "enhanced":
            if "analyst_actions" not in fact_types:
                issues.append(QualityIssue(
                    issue_type="missing_analyst_actions",
                    severity="info",
                    message="Missing analyst action evidence for enhanced company report.",
                    affected_fact_types=["analyst_actions"],
                    retrieval_needed=True,
                    suggested_task_type="fetch_analyst_actions",
                ))
            if "earnings_or_guidance" not in fact_types:
                issues.append(QualityIssue(
                    issue_type="missing_earnings_guidance",
                    severity="info",
                    message="Missing earnings and guidance evidence for enhanced company report.",
                    affected_fact_types=["earnings_or_guidance"],
                    retrieval_needed=True,
                    suggested_task_type="fetch_earnings_guidance",
                ))
            if "macro_context" not in fact_types:
                issues.append(QualityIssue(
                    issue_type="missing_macro_context",
                    severity="info",
                    message="Missing macro context evidence for enhanced company report.",
                    affected_fact_types=["macro_context"],
                    retrieval_needed=True,
                    suggested_task_type="fetch_macro_context",
                ))

        issues.extend(_partial_comparison_issues(run))
        issues.extend(_claim_verification_issues(run))
        issues.extend(_guardrail_issues(run))
        return issues


def _first_fact(run: ResearchRunState, fact_type: str) -> VerifiedFact | None:
    return next((fact for fact in run.verified_facts if fact.fact_type == fact_type), None)


def _plan_needs(run: ResearchRunState, key: str) -> bool:
    if run.attribution_plan is None:
        return False
    return any(need.key == key for need in run.attribution_plan.needs)


def _partial_comparison_issues(run: ResearchRunState) -> list[QualityIssue]:
    raw_ids_by_type = {
        fact.raw_fact_id or fact.id: fact.fact_type
        for fact in run.verified_facts
        if fact.fact_type in {"sector_move", "peer_moves"} and fact.verification_status == "partial"
    }
    if not raw_ids_by_type:
        return []

    issues: list[QualityIssue] = []
    for cause in run.attribution_causes:
        if cause.level != "likely_factor":
            continue
        affected_ids = [fact_id for fact_id in cause.support_fact_ids if fact_id in raw_ids_by_type]
        if not affected_ids:
            continue
        issues.append(QualityIssue(
            issue_type="partial_comparison_supports_likely_factor",
            severity="warning",
            message="Likely attribution uses partial sector or peer comparison evidence.",
            affected_fact_types=sorted({raw_ids_by_type[fact_id] for fact_id in affected_ids}),
            affected_fact_ids=affected_ids,
            retrieval_needed=False,
            suggested_task_type="rerender_with_downgrade",
        ))
    return issues


def _claim_verification_issues(run: ResearchRunState) -> list[QualityIssue]:
    if run.claim_verification is None:
        return []
    issues: list[QualityIssue] = []
    for issue in run.claim_verification.issues:
        if issue.issue_type != "direct_trading_advice":
            continue
        issues.append(QualityIssue(
            issue_type="direct_trading_advice",
            severity="error",
            message=issue.message,
            affected_fact_ids=issue.fact_ids,
            retrieval_needed=False,
        ))
    return issues


def _guardrail_issues(run: ResearchRunState) -> list[QualityIssue]:
    if run.guardrail is None or run.guardrail.passed:
        return []
    failed_checks = [check.name for check in run.guardrail.checks if not check.passed]
    return [QualityIssue(
        issue_type="guardrail_failed",
        severity="error",
        message="Research output failed guardrail checks.",
        affected_fact_types=failed_checks,
        retrieval_needed=False,
    )]
