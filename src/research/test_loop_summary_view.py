from src.research.loop_engine import LoopResult, append_loop_summary
from src.research.models import ResearchRunState


def test_quality_passed_without_iterations_renders_quality_audit_result_heading() -> None:
    run = ResearchRunState.start("美光 MU 最近为什么大跌？")
    result = LoopResult(
        initial_run=run,
        final_run=run,
        iterations=[],
        stop_reason="quality_passed",
        quality_delta={
            "added_fact_types": [],
            "remaining_missing_fact_types": ["analyst_actions"],
            "before_attribution_level": "likely_factor",
            "after_attribution_level": "likely_factor",
        },
    )

    output = append_loop_summary("# Report", result)

    assert "## 质量审计结果" in output
    assert "## 本轮质量改进" not in output
    assert "未触发补证据" in output
    assert "仍缺证据：分析师动作" in output


def test_repaired_iteration_renders_quality_improvement_heading() -> None:
    run = ResearchRunState.start("美光 MU 最近为什么大跌？")
    result = LoopResult(
        initial_run=run,
        final_run=run,
        iterations=[object()],  # type: ignore[list-item]
        stop_reason="max_loops_reached",
        quality_delta={
            "added_fact_types": ["peer_moves"],
            "remaining_missing_fact_types": [],
            "before_attribution_level": "candidate_factor",
            "after_attribution_level": "likely_factor",
        },
    )

    output = append_loop_summary("# Report", result)

    assert "## 本轮质量改进" in output
    assert "已执行 1 次补证据" in output
    assert "新增证据：同行走势" in output



def test_no_actionable_tasks_without_iterations_renders_quality_audit_result_heading() -> None:
    run = ResearchRunState.start("美光 MU 最近为什么大跌？")
    result = LoopResult(
        initial_run=run,
        final_run=run,
        iterations=[],
        stop_reason="no_actionable_tasks",
        quality_delta={
            "added_fact_types": [],
            "remaining_missing_fact_types": ["macro_context"],
            "before_attribution_level": "likely_factor",
            "after_attribution_level": "likely_factor",
        },
    )

    output = append_loop_summary("# Report", result)

    assert "## 质量审计结果" in output
    assert "## 本轮质量改进" not in output
    assert "未执行补证据" in output
