"""Whitelist evidence repair tasks for the bounded research loop."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

from src.research.models import ResearchRunState
from src.research.quality_auditor import QualityIssue
from src.research.tool_provider import ToolResultBundle


TaskType = Literal["retry_news_zh", "fetch_sector_history", "fetch_peer_history", "fetch_analyst_actions", "fetch_earnings_guidance", "fetch_macro_context", "rerender_with_downgrade"]
TaskStatus = Literal["completed", "failed", "skipped"]
ToolResultSlot = Literal["news", "sector_history", "peer_history", "analyst_actions", "earnings_guidance", "macro_context"]


@dataclass(frozen=True)
class EvidenceTask:
    task_type: TaskType
    reason: str
    target_symbol: str
    required_fact_type: str | None = None
    max_attempts: int = 1


@dataclass(frozen=True)
class EvidenceTaskResult:
    task_type: str
    status: TaskStatus
    tool_result_slot: ToolResultSlot | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class EvidenceTaskPlanner:
    """Map quality issues to deterministic whitelisted evidence tasks."""

    def plan(self, issues: list[QualityIssue], run: ResearchRunState) -> list[EvidenceTask]:
        tasks: list[EvidenceTask] = []
        seen: set[str] = set()
        target_symbol = _target_symbol(run)

        for issue in issues:
            task = _task_for_issue(issue, target_symbol)
            if task is None or task.task_type in seen:
                continue
            seen.add(task.task_type)
            tasks.append(task)
        return tasks


def merge_task_results_into_bundle(
    base_bundle: ToolResultBundle,
    task_results: list[EvidenceTaskResult],
) -> ToolResultBundle:
    """Return an enhanced bundle without mutating the base bundle."""

    updates: dict[str, dict[str, Any]] = {}
    for result in task_results:
        if result.status != "completed" or result.tool_result_slot is None:
            continue
        updates[result.tool_result_slot] = result.payload

    return replace(base_bundle, **updates)


def _target_symbol(run: ResearchRunState) -> str:
    if run.resolved_entity is not None:
        return run.resolved_entity.symbol
    return ""


def _task_for_issue(issue: QualityIssue, target_symbol: str) -> EvidenceTask | None:
    if issue.issue_type in {"missing_news_events", "partial_news_events"} and issue.suggested_task_type == "retry_news_zh":
        return EvidenceTask(
            task_type="retry_news_zh",
            reason=issue.message,
            target_symbol=target_symbol,
            required_fact_type="news_events",
        )

    if issue.issue_type == "missing_sector_move" and issue.suggested_task_type == "fetch_sector_history":
        return EvidenceTask(
            task_type="fetch_sector_history",
            reason=issue.message,
            target_symbol=target_symbol,
            required_fact_type="sector_move",
        )

    if issue.issue_type == "missing_peer_moves" and issue.suggested_task_type == "fetch_peer_history":
        return EvidenceTask(
            task_type="fetch_peer_history",
            reason=issue.message,
            target_symbol=target_symbol,
            required_fact_type="peer_moves",
        )


    if issue.issue_type == "missing_analyst_actions" and issue.suggested_task_type == "fetch_analyst_actions":
        return EvidenceTask(
            task_type="fetch_analyst_actions",
            reason=issue.message,
            target_symbol=target_symbol,
            required_fact_type="analyst_actions",
        )

    if issue.issue_type == "missing_earnings_guidance" and issue.suggested_task_type == "fetch_earnings_guidance":
        return EvidenceTask(
            task_type="fetch_earnings_guidance",
            reason=issue.message,
            target_symbol=target_symbol,
            required_fact_type="earnings_or_guidance",
        )

    if issue.issue_type == "missing_macro_context" and issue.suggested_task_type == "fetch_macro_context":
        return EvidenceTask(
            task_type="fetch_macro_context",
            reason=issue.message,
            target_symbol=target_symbol,
            required_fact_type="macro_context",
        )

    if (
        issue.issue_type == "partial_comparison_supports_likely_factor"
        and issue.suggested_task_type == "rerender_with_downgrade"
    ):
        return EvidenceTask(
            task_type="rerender_with_downgrade",
            reason=issue.message,
            target_symbol=target_symbol,
        )

    return None
