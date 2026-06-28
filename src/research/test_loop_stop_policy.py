from src.research.evidence_tasks import EvidenceTaskResult
from src.research.loop_stop_policy import decide_loop_stop
from src.research.quality_auditor import QualityIssue


def _issue(issue_type: str, fact_type: str = "peer_moves") -> QualityIssue:
    return QualityIssue(
        issue_type=issue_type,
        severity="warning",
        message=f"missing {fact_type}",
        affected_fact_types=[fact_type],
        retrieval_needed=True,
        suggested_task_type="fetch_peer_history",
    )


def test_decision_quality_passed_when_no_issues() -> None:
    decision = decide_loop_stop(issues_before=[], planned_tasks=[], task_results=[], quality_delta={}, guardrail_passed=True)

    assert decision.stop_reason == "quality_passed"
    assert decision.quality_status == "passed"
    assert decision.should_continue is False
    assert "达到当前质量标准" in decision.user_message


def test_decision_no_actionable_tasks_when_audit_has_unplanned_issues() -> None:
    decision = decide_loop_stop(
        issues_before=[_issue("semantic_support_weak", "semantic_support")],
        planned_tasks=[],
        task_results=[],
        quality_delta={},
        guardrail_passed=True,
    )

    assert decision.stop_reason == "no_actionable_tasks"
    assert decision.quality_status == "not_improved"
    assert decision.can_continue is False
    assert "没有安全的白名单任务" in decision.user_message


def test_decision_all_tasks_failed() -> None:
    decision = decide_loop_stop(
        issues_before=[_issue("missing_peer_moves")],
        planned_tasks=["fetch_peer_history"],
        task_results=[EvidenceTaskResult("fetch_peer_history", "failed", error="timeout")],
        quality_delta={},
        guardrail_passed=True,
    )

    assert decision.stop_reason == "all_tasks_failed"
    assert decision.quality_status == "not_improved"
    assert decision.should_continue is True
    assert decision.can_continue is False


def test_decision_no_quality_improvement_when_tasks_add_nothing() -> None:
    decision = decide_loop_stop(
        issues_before=[_issue("missing_peer_moves")],
        planned_tasks=["fetch_peer_history"],
        task_results=[EvidenceTaskResult("fetch_peer_history", "skipped")],
        quality_delta={"added_fact_types": [], "resolved_missing_fact_types": [], "before_attribution_level": "candidate_factor", "after_attribution_level": "candidate_factor"},
        guardrail_passed=True,
        issues_after=[_issue("missing_peer_moves")],
    )

    assert decision.stop_reason == "no_quality_improvement"
    assert decision.quality_status == "not_improved"
    assert "没有拿到新的可核验证据" in decision.user_message


def test_decision_max_loops_reached_with_improvement() -> None:
    decision = decide_loop_stop(
        issues_before=[_issue("missing_peer_moves")],
        planned_tasks=["fetch_peer_history"],
        task_results=[EvidenceTaskResult("fetch_peer_history", "completed", "peer_history", {"items": [1]})],
        quality_delta={"added_fact_types": ["peer_moves"], "resolved_missing_fact_types": ["peer_moves"], "before_attribution_level": "candidate_factor", "after_attribution_level": "likely_factor"},
        guardrail_passed=True,
        issues_after=[],
        loop_index=1,
        max_loops=1,
    )

    assert decision.stop_reason == "max_loops_reached_with_improvement"
    assert decision.quality_status == "passed"
    assert decision.should_continue is False
    assert "报告变好了" in decision.user_message


def test_decision_treats_optional_missing_facts_as_deliverable_when_audit_passed() -> None:
    decision = decide_loop_stop(
        issues_before=[_issue("missing_peer_moves")],
        planned_tasks=["fetch_peer_history"],
        task_results=[EvidenceTaskResult("fetch_peer_history", "completed", "peer_history", {"items": [1]})],
        quality_delta={
            "added_fact_types": ["peer_moves"],
            "resolved_missing_fact_types": ["peer_moves"],
            "remaining_missing_fact_types": ["analyst_actions", "macro_context"],
            "before_attribution_level": "candidate_factor",
            "after_attribution_level": "likely_factor",
        },
        guardrail_passed=True,
        issues_after=[],
        loop_index=1,
        max_loops=1,
    )

    assert decision.stop_reason == "max_loops_reached_with_improvement"
    assert decision.quality_status == "passed"
    assert decision.should_continue is False
    assert decision.remaining_gaps == []


def test_decision_partial_enhanced_evidence_when_some_enhanced_gaps_remain() -> None:
    decision = decide_loop_stop(
        issues_before=[_issue("missing_analyst_actions", "analyst_actions"), _issue("missing_macro_context", "macro_context")],
        planned_tasks=["fetch_analyst_actions", "fetch_macro_context"],
        task_results=[EvidenceTaskResult("fetch_analyst_actions", "completed", "analyst_actions", {"items": [1]})],
        quality_delta={"added_fact_types": ["analyst_actions"], "resolved_missing_fact_types": ["analyst_actions"], "before_attribution_level": "likely_factor", "after_attribution_level": "likely_factor"},
        guardrail_passed=True,
        issues_after=[_issue("missing_macro_context", "macro_context")],
        research_depth="enhanced",
        loop_index=1,
        max_loops=1,
    )

    assert decision.stop_reason == "partial_enhanced_evidence"
    assert decision.quality_status == "improved_but_incomplete"
    assert decision.remaining_gaps == ["macro_context"]
    assert "增强层只补到部分证据" in decision.user_message


def test_decision_guardrail_blocked() -> None:
    decision = decide_loop_stop(issues_before=[], planned_tasks=[], task_results=[], quality_delta={}, guardrail_passed=False)

    assert decision.stop_reason == "guardrail_blocked"
    assert decision.quality_status == "blocked"
    assert decision.can_continue is False
