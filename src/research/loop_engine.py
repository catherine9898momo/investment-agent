"""Bounded evidence repair loop built around enhanced ToolResultBundle rebuilds."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from src.research.evidence_tasks import (
    EvidenceTask,
    EvidenceTaskPlanner,
    EvidenceTaskResult,
    merge_task_results_into_bundle,
)
from src.research.loop_stop_policy import LoopStopDecision, decide_loop_stop
from src.research.models import ResearchRunState
from src.research.query_intake import QueryUnderstanding
from src.research.quality_auditor import QualityIssue, ReportQualityAuditor
from src.research.tool_provider import ToolResultBundle
from src.research.trace import TraceLogger


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
TaskExecutor = Callable[[list[EvidenceTask], ResearchRunState], list[EvidenceTaskResult]]


@dataclass(frozen=True)
class LoopIteration:
    index: int
    quality_issues_before: list[QualityIssue]
    evidence_tasks: list[EvidenceTask]
    task_results: list[EvidenceTaskResult]
    quality_issues_after: list[QualityIssue] = field(default_factory=list)
    stop_reason: str | None = None


@dataclass(frozen=True)
class LoopResult:
    initial_run: ResearchRunState
    final_run: ResearchRunState
    iterations: list[LoopIteration]
    stop_reason: StopReason
    quality_delta: dict[str, Any] = field(default_factory=dict)
    stop_decision: LoopStopDecision | None = None


def build_research_run_with_loop_from_bundle(
    user_query: str,
    base_bundle: ToolResultBundle,
    *,
    understanding: QueryUnderstanding,
    task_executor: TaskExecutor,
    synthesizer_name: str = "mock",
    max_loops: int = 1,
    quality_threshold: str = "normal",
    research_depth: str = "normal",
) -> LoopResult:
    """Run one bounded evidence repair loop by rebuilding from an enhanced bundle."""

    from src.agents.research_demo import build_research_run_from_bundle

    auditor = ReportQualityAuditor()
    planner = EvidenceTaskPlanner()
    initial_run = build_research_run_from_bundle(
        user_query,
        base_bundle,
        synthesizer_name=synthesizer_name,
        symbol=understanding.entity.symbol,
        understanding=understanding,
    )
    current_run = initial_run
    current_bundle = base_bundle
    iterations: list[LoopIteration] = []
    final_decision: LoopStopDecision | None = None

    for index in range(1, max_loops + 1):
        issues_before = auditor.audit(current_run, research_depth=research_depth)
        if current_run.guardrail and not current_run.guardrail.passed:
            final_decision = decide_loop_stop(
                issues_before=issues_before,
                planned_tasks=[],
                task_results=[],
                quality_delta=compute_quality_delta(initial_run, current_run),
                guardrail_passed=False,
                research_depth=research_depth,
                loop_index=index - 1,
                max_loops=max_loops,
            )
            break

        if not issues_before:
            final_decision = decide_loop_stop(
                issues_before=[],
                planned_tasks=[],
                task_results=[],
                quality_delta=compute_quality_delta(initial_run, current_run),
                guardrail_passed=True,
                research_depth=research_depth,
                loop_index=index - 1,
                max_loops=max_loops,
            )
            break

        tasks = planner.plan(issues_before, current_run)
        task_types = [task.task_type for task in tasks]
        if not tasks:
            final_decision = decide_loop_stop(
                issues_before=issues_before,
                planned_tasks=[],
                task_results=[],
                quality_delta=compute_quality_delta(initial_run, current_run),
                guardrail_passed=True,
                research_depth=research_depth,
                loop_index=index - 1,
                max_loops=max_loops,
            )
            break

        task_results = task_executor(tasks, current_run)
        if task_results and all(result.status == "failed" for result in task_results):
            final_decision = decide_loop_stop(
                issues_before=issues_before,
                planned_tasks=task_types,
                task_results=task_results,
                quality_delta=compute_quality_delta(initial_run, current_run),
                guardrail_passed=True,
                research_depth=research_depth,
                loop_index=index,
                max_loops=max_loops,
            )
            iterations.append(LoopIteration(index, issues_before, tasks, task_results, [], final_decision.stop_reason))
            break

        enhanced_bundle = merge_task_results_into_bundle(current_bundle, task_results)
        next_run = build_research_run_from_bundle(
            user_query,
            enhanced_bundle,
            synthesizer_name=synthesizer_name,
            symbol=understanding.entity.symbol,
            understanding=understanding,
        )
        issues_after = auditor.audit(next_run, research_depth=research_depth)
        delta = compute_quality_delta(current_run, next_run)
        final_decision = decide_loop_stop(
            issues_before=issues_before,
            planned_tasks=task_types,
            task_results=task_results,
            quality_delta=delta,
            guardrail_passed=not (next_run.guardrail and not next_run.guardrail.passed),
            issues_after=issues_after,
            research_depth=research_depth,
            loop_index=index,
            max_loops=max_loops,
        )
        iterations.append(LoopIteration(index, issues_before, tasks, task_results, issues_after, final_decision.stop_reason))

        _append_loop_trace(
            next_run,
            initial_run,
            index,
            quality_threshold,
            issues_before,
            tasks,
            task_results,
            issues_after,
            final_decision.stop_reason,
        )

        current_run = next_run
        current_bundle = enhanced_bundle
        break

    quality_delta = compute_quality_delta(initial_run, current_run)
    if final_decision is None:
        final_decision = decide_loop_stop(
            issues_before=[],
            planned_tasks=[],
            task_results=[],
            quality_delta=quality_delta,
            guardrail_passed=not (current_run.guardrail and not current_run.guardrail.passed),
            research_depth=research_depth,
            loop_index=len(iterations),
            max_loops=max_loops,
        )
    result = LoopResult(initial_run, current_run, iterations, final_decision.stop_reason, quality_delta, final_decision)
    current_run.final_output = append_loop_summary(current_run.final_output or "", result)
    return result

def compute_quality_delta(before: ResearchRunState, after: ResearchRunState) -> dict[str, Any]:
    before_types = {fact.fact_type for fact in before.verified_facts}
    after_types = {fact.fact_type for fact in after.verified_facts}
    before_missing = {fact.fact_type for fact in before.missing_facts}
    after_missing = {fact.fact_type for fact in after.missing_facts}
    return {
        "added_fact_types": sorted(after_types - before_types),
        "remaining_missing_fact_types": sorted(after_missing),
        "resolved_missing_fact_types": sorted(before_missing - after_missing),
        "before_attribution_level": before.attribution_causes[0].level if before.attribution_causes else None,
        "after_attribution_level": after.attribution_causes[0].level if after.attribution_causes else None,
    }


def append_loop_summary(output: str, result: LoopResult) -> str:
    delta = result.quality_delta
    added = _fact_types_label_or_raw(delta.get("added_fact_types") or [])
    remaining = _fact_types_label_or_raw(delta.get("remaining_missing_fact_types") or [])
    before_level = delta.get("before_attribution_level")
    after_level = delta.get("after_attribution_level")
    level_change = _format_level_change(before_level, after_level)
    executed_count = len(result.iterations)
    decision_lines = _format_loop_stop_decision_lines(result)

    if executed_count == 0:
        status_line = (
            f"normal 标准已通过，未触发补证据；停止原因：{_stop_reason_label(result.stop_reason)}。"
            if result.stop_reason == "quality_passed"
            else f"审计后未执行补证据；停止原因：{_stop_reason_label(result.stop_reason)}。"
        )
        summary = [
            "",
            "## 质量审计结果",
            f"- Loop 状态：{status_line}",
            *decision_lines,
            f"- 新增证据：{added}。",
            f"- 仍缺证据：{remaining}。",
            f"- 归因等级变化：{level_change}。",
        ]
        if result.final_run.trace_path:
            summary.append(f"- Trace 日志：{result.final_run.trace_path}")
        return output.rstrip() + "\n" + "\n".join(summary)

    summary = [
        "",
        "## 本轮质量改进",
        f"- Loop 状态：已执行 {executed_count} 次补证据；停止原因：{_stop_reason_label(result.stop_reason)}。",
        *decision_lines,
        f"- 新增证据：{added}。",
        f"- 仍缺证据：{remaining}。",
        f"- 归因等级变化：{level_change}。",
    ]
    if result.final_run.trace_path:
        summary.append(f"- Trace 日志：{result.final_run.trace_path}")
    return output.rstrip() + "\n" + "\n".join(summary)


def _format_loop_stop_decision_lines(result: LoopResult) -> list[str]:
    decision = result.stop_decision
    if decision is None:
        return []
    lines = [
        f"- 质量状态：{_quality_status_label(decision.quality_status)}。",
        f"- 为什么停：{decision.user_message}",
        f"- 是否建议继续：{'是' if decision.should_continue else '否'}。",
        f"- 是否还能继续：{'是' if decision.can_continue else '否'}。",
    ]
    improvement_line = _format_human_improvement_summary(result)
    if improvement_line:
        lines.append("- 改善说明：" + improvement_line + "。")
    if decision.remaining_actionable_tasks:
        lines.append("- 剩余可执行任务：" + ", ".join(decision.remaining_actionable_tasks) + "。")
    return lines


def _quality_status_label(status: str) -> str:
    return {
        "passed": "已达到当前质量标准",
        "improved_but_incomplete": "已改善但仍有缺口",
        "not_improved": "未获得实质改善",
        "blocked": "被护栏阻断",
    }.get(status, status)

def _format_level_change(before_level: object, after_level: object) -> str:
    if not before_level and not after_level:
        return "无"
    before_label = _attribution_level_label(str(before_level)) if before_level else "无"
    after_label = _attribution_level_label(str(after_level)) if after_level else "无"
    return f"{before_label} -> {after_label}"


def _stop_reason_label(reason: str) -> str:
    return {
        "quality_passed": "质量已达标",
        "max_loops_reached_with_improvement": "本轮补证据已带来改善，且达到本次 loop 预算",
        "max_loops_reached_without_full_quality": "已有改善但仍有缺口，且达到本次 loop 预算",
        "no_actionable_tasks": "没有可安全执行的补证据任务",
        "all_tasks_failed": "补证据任务全部失败",
        "guardrail_blocked": "安全或证据护栏阻断",
        "no_quality_improvement": "本轮没有带来实质质量改善",
        "partial_enhanced_evidence": "增强证据只补到一部分",
    }.get(reason, reason)


def _fact_types_label_or_raw(fact_types: list[str]) -> str:
    if not fact_types:
        return "无"
    labels = _fact_type_labels(fact_types)
    return labels or ", ".join(fact_types)


def _format_human_improvement_summary(result: LoopResult) -> str:
    delta = result.quality_delta
    parts: list[str] = []
    added = _fact_types_label_or_raw(delta.get("added_fact_types") or [])
    resolved = _fact_types_label_or_raw(delta.get("resolved_missing_fact_types") or [])
    before_level = delta.get("before_attribution_level")
    after_level = delta.get("after_attribution_level")
    if added != "无":
        parts.append(f"新增了{added}，报告不再只靠价格和新闻标题判断")
    if resolved != "无":
        parts.append(f"补齐了{resolved}对应的关键缺口")
    if before_level and after_level and before_level != after_level:
        parts.append(f"归因等级从{_attribution_level_label(before_level)}提升到{_attribution_level_label(after_level)}，说明证据从线索级增强到可支持较明确解释")
    return "；".join(parts)


def _append_loop_trace(
    run: ResearchRunState,
    initial_run: ResearchRunState,
    iteration_index: int,
    quality_threshold: str,
    issues_before: list[QualityIssue],
    tasks: list[EvidenceTask],
    task_results: list[EvidenceTaskResult],
    issues_after: list[QualityIssue],
    stop_reason: StopReason,
) -> None:
    trace = TraceLogger(run)
    trace.append("loop_started", {
        "initial_run_id": initial_run.run_id,
        "final_run_id": run.run_id,
        "max_loops": 1,
        "quality_threshold": quality_threshold,
    })
    trace.append("audit_completed", {"iteration_index": iteration_index, "issues": issues_before})
    trace.append("evidence_tasks_planned", {"iteration_index": iteration_index, "tasks": tasks})
    for result in task_results:
        trace.append(
            "evidence_task_completed" if result.status == "completed" else "evidence_task_failed",
            {"iteration_index": iteration_index, "result": result},
        )
    trace.append("enhanced_bundle_built", {"iteration_index": iteration_index})
    trace.append("run_rebuilt_from_enhanced_bundle", {
        "iteration_index": iteration_index,
        "initial_run_id": initial_run.run_id,
        "rebuilt_run_id": run.run_id,
    })
    trace.append("audit_completed", {"iteration_index": iteration_index, "phase": "after", "issues": issues_after})
    trace.append("loop_stopped", {"iteration_index": iteration_index, "stop_reason": stop_reason})


def render_loop_comparison(result: LoopResult) -> str:
    delta = result.quality_delta
    before_types = _user_visible_fact_types(sorted({fact.fact_type for fact in result.initial_run.verified_facts}))
    after_types = _user_visible_fact_types(sorted({fact.fact_type for fact in result.final_run.verified_facts}))
    added = delta.get("added_fact_types") or []
    before_level = delta.get("before_attribution_level") or "无"
    after_level = delta.get("after_attribution_level") or "无"
    before_score = _attribution_level_score(before_level)
    after_score = _attribution_level_score(after_level)
    added_labels = _fact_type_labels(added)
    before_level_label = _attribution_level_label(before_level)
    after_level_label = _attribution_level_label(after_level)
    if added:
        added_meaning = "这说明报告不再只依赖价格和新闻标题，而是加入了同行走势、分析师动作、财报/指引和宏观背景。"
        level_meaning = "这说明系统从“有线索但证据不足”升级到“已有同窗口对照支持”，所以结论可以更具体，但仍不能写成确定原因。"
    else:
        added_meaning = "本轮 loop 没有拿到新的可核验证据，所以 run_1 没有获得新的事实基础。"
        level_meaning = "归因等级没有变化，说明这次 live loop 没有实际改善报告质量；需要接入对应 live 数据源或换一个会触发核心缺口的 case。"
    lines = [
        "",
        "## Loop 效果对比",
        "",
        "### Loop 前",
        f"- 报告只能给出“{before_level_label}”：已有证据是 { _fact_type_labels(before_types) or '无' }。",
        "- 含义：初稿可以看到价格和部分背景线索，但还缺少足够的对照或公司研究增强证据，所以只能保守表达。",
        "",
        "### Loop 后",
        f"- 新增证据：{added_labels or '无'}。",
        f"- 含义：{added_meaning}",
        f"- 归因等级变化：{before_level_label} -> {after_level_label}。",
        f"- 含义：{level_meaning}",
        "",
        "### 为什么这是更好的报告",
        f"- 证据覆盖：{len(before_types)} 类 -> {len(after_types)} 类。",
        f"- 含义：{'这说明 run_1 的判断覆盖了公司、行业和宏观三层背景，用户能看到为什么这个解释更可信，而不是只看到一个结论。' if added else '这说明证据覆盖没有扩大，本次 loop 只是重跑流程，没有带来实质报告增强。'}",
        f"- 安全性：guardrail {_guardrail_label(result.initial_run)} -> {_guardrail_label(result.final_run)}，说明补证据没有换来更激进或不合规的交易建议。",
        "",
        "### 机器指标",
        f"- verified_fact_types: {len(before_types)} -> {len(after_types)}",
        f"- attribution_level_score: {before_score:g} -> {after_score:g}",
        f"- attribution_level: {before_level} -> {after_level}",
    ]
    return "\n".join(lines)


def _user_visible_fact_types(fact_types: list[str]) -> list[str]:
    visible = {
        "price_move",
        "news_events",
        "sector_move",
        "peer_moves",
        "analyst_actions",
        "earnings_or_guidance",
        "macro_context",
        "corporate_actions",
        "user_preferences",
    }
    return [fact_type for fact_type in fact_types if fact_type in visible]


def _fact_type_labels(fact_types: list[str]) -> str:
    mapping = {
        "price_move": "价格变化",
        "news_events": "新闻线索",
        "sector_move": "板块/指数走势",
        "peer_moves": "同行走势",
        "analyst_actions": "分析师动作",
        "earnings_or_guidance": "财报/指引",
        "macro_context": "宏观背景",
        "corporate_actions": "公司行动",
        "user_preferences": "用户偏好",
    }
    labels = [mapping[item] for item in fact_types if item in mapping]
    return "、".join(labels)


def _attribution_level_label(level: str) -> str:
    return {
        "unsupported": "证据不支持",
        "background_context": "背景信息",
        "candidate_factor": "候选因素",
        "likely_factor": "较可能因素",
        "confirmed_cause": "已确认原因",
    }.get(level, level)


def _attribution_level_score(level: str) -> float:
    return {
        "unsupported": 0.0,
        "background_context": 0.5,
        "candidate_factor": 1.0,
        "likely_factor": 2.0,
        "confirmed_cause": 3.0,
    }.get(level, 0.0)


def _guardrail_label(run: ResearchRunState) -> str:
    if run.guardrail is None:
        return "UNKNOWN"
    return "PASS" if run.guardrail.passed else "BLOCKED"
