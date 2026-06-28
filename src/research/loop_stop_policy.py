"""Product-facing stop decisions for bounded research loops."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.research.evidence_tasks import EvidenceTaskResult
from src.research.quality_auditor import QualityIssue


StopReason = Literal[
    "quality_passed",
    "max_loops_reached_with_improvement",
    "max_loops_reached_without_full_quality",
    "no_actionable_tasks",
    "all_tasks_failed",
    "guardrail_blocked",
    "no_quality_improvement",
    "partial_enhanced_evidence",
]
QualityStatus = Literal["passed", "improved_but_incomplete", "not_improved", "blocked"]

_ENHANCED_FACT_TYPES = {"analyst_actions", "earnings_or_guidance", "macro_context"}


@dataclass(frozen=True)
class LoopStopDecision:
    stop_reason: StopReason
    quality_status: QualityStatus
    user_message: str
    should_continue: bool
    can_continue: bool
    remaining_actionable_tasks: list[str] = field(default_factory=list)
    remaining_gaps: list[str] = field(default_factory=list)
    improvement_summary: list[str] = field(default_factory=list)


def decide_loop_stop(
    *,
    issues_before: list[QualityIssue],
    planned_tasks: list[str],
    task_results: list[EvidenceTaskResult],
    quality_delta: dict[str, Any],
    guardrail_passed: bool,
    issues_after: list[QualityIssue] | None = None,
    research_depth: str = "normal",
    loop_index: int = 0,
    max_loops: int = 1,
) -> LoopStopDecision:
    """Return a product-readable decision for why the loop should stop."""

    if not guardrail_passed:
        return LoopStopDecision(
            stop_reason="guardrail_blocked",
            quality_status="blocked",
            user_message="报告触发安全或证据护栏，不能作为最终输出。",
            should_continue=False,
            can_continue=False,
            remaining_gaps=_issue_fact_types(issues_after or issues_before),
        )

    if not issues_before:
        return LoopStopDecision(
            stop_reason="quality_passed",
            quality_status="passed",
            user_message="核心证据已达到当前质量标准，继续补证据的边际收益较低。",
            should_continue=False,
            can_continue=False,
        )

    if not planned_tasks:
        return LoopStopDecision(
            stop_reason="no_actionable_tasks",
            quality_status="not_improved",
            user_message="系统发现了质量问题，但当前没有安全的白名单任务可以处理它。",
            should_continue=True,
            can_continue=False,
            remaining_gaps=_issue_fact_types(issues_before),
        )

    if task_results and all(result.status == "failed" for result in task_results):
        return LoopStopDecision(
            stop_reason="all_tasks_failed",
            quality_status="not_improved",
            user_message="系统尝试补证据，但所有任务都失败；继续重试大概率不会改善。",
            should_continue=True,
            can_continue=False,
            remaining_actionable_tasks=planned_tasks,
            remaining_gaps=_issue_fact_types(issues_before),
        )

    added = list(quality_delta.get("added_fact_types") or [])
    resolved = list(quality_delta.get("resolved_missing_fact_types") or [])
    before_level = quality_delta.get("before_attribution_level")
    after_level = quality_delta.get("after_attribution_level")
    improved = bool(added or resolved or _level_score(after_level) > _level_score(before_level))
    remaining_gaps = _issue_fact_types(issues_after) if issues_after is not None else list(quality_delta.get("remaining_missing_fact_types") or [])

    if not improved:
        return LoopStopDecision(
            stop_reason="no_quality_improvement",
            quality_status="not_improved",
            user_message="本轮 loop 没有拿到新的可核验证据，因此没有改善报告质量。",
            should_continue=True,
            can_continue=False,
            remaining_actionable_tasks=planned_tasks,
            remaining_gaps=remaining_gaps,
        )

    enhanced_remaining = [gap for gap in remaining_gaps if gap in _ENHANCED_FACT_TYPES]
    if research_depth == "enhanced" and enhanced_remaining and any(fact in _ENHANCED_FACT_TYPES for fact in added):
        return LoopStopDecision(
            stop_reason="partial_enhanced_evidence",
            quality_status="improved_but_incomplete",
            user_message="短期归因已经可交付；公司研究增强层只补到部分证据，未补齐项会保留为后续研究缺口。",
            should_continue=True,
            can_continue=loop_index < max_loops,
            remaining_actionable_tasks=planned_tasks if loop_index < max_loops else [],
            remaining_gaps=enhanced_remaining,
            improvement_summary=_improvement_summary(added, resolved, before_level, after_level),
        )

    if loop_index >= max_loops:
        if remaining_gaps:
            return LoopStopDecision(
                stop_reason="max_loops_reached_without_full_quality",
                quality_status="improved_but_incomplete",
                user_message="报告已有改善，但仍未完全达到目标质量；本次停止是因为 loop 预算用完。",
                should_continue=True,
                can_continue=False,
                remaining_gaps=remaining_gaps,
                improvement_summary=_improvement_summary(added, resolved, before_level, after_level),
            )
        return LoopStopDecision(
            stop_reason="max_loops_reached_with_improvement",
            quality_status="passed",
            user_message="本轮补证据让报告变好了，并已达到本次 loop 预算；当前报告可以交付。",
            should_continue=False,
            can_continue=False,
            improvement_summary=_improvement_summary(added, resolved, before_level, after_level),
        )

    return LoopStopDecision(
        stop_reason="max_loops_reached_with_improvement",
        quality_status="passed",
        user_message="本轮补证据让报告变好了；当前报告可以交付。",
        should_continue=False,
        can_continue=True,
        improvement_summary=_improvement_summary(added, resolved, before_level, after_level),
    )


def _issue_fact_types(issues: list[QualityIssue]) -> list[str]:
    fact_types: list[str] = []
    for issue in issues:
        for fact_type in issue.affected_fact_types:
            if fact_type not in fact_types:
                fact_types.append(fact_type)
    return fact_types


def _level_score(level: object) -> float:
    return {
        "unsupported": 0.0,
        "background_context": 0.5,
        "candidate_factor": 1.0,
        "likely_factor": 2.0,
        "confirmed_cause": 3.0,
    }.get(str(level), 0.0)


def _improvement_summary(added: list[str], resolved: list[str], before_level: object, after_level: object) -> list[str]:
    summary: list[str] = []
    if added:
        summary.append("新增证据：" + ", ".join(added))
    if resolved:
        summary.append("解决缺口：" + ", ".join(resolved))
    if before_level != after_level:
        summary.append(f"归因等级：{before_level} -> {after_level}")
    return summary
