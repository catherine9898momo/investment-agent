from src.research.evidence_tasks import EvidenceTaskResult
from src.research.loop_engine import build_research_run_with_loop_from_bundle, render_loop_comparison
from src.research.query_intake import understand_query
from src.research.tool_provider import ToolResultBundle


QUERY = "美光 MU 最近为什么大跌？"


def _base_bundle_missing_peer_and_enhanced() -> ToolResultBundle:
    return ToolResultBundle(
        data_source="fixture",
        preferences={"style": "价值投资研究优先"},
        quote={"symbol": "MU", "price": 94.0, "previous_close": 100.0, "change_pct": -6.0, "currency": "USD"},
        history={
            "symbol": "MU",
            "period": "5d",
            "bars": [
                {"date": "2026-06-24", "close": 100.0},
                {"date": "2026-06-25", "close": 96.0},
                {"date": "2026-06-26", "close": 94.0},
            ],
        },
        news={"query": "Micron", "items": [{"title": "Micron shares fall with chip sector", "source": "Fixture"}]},
        corporate_actions={"symbol": "MU", "actions": [], "splits_count": 0, "cumulative_split_factor": 1.0, "source": "fixture"},
        sector_history={
            "period": "5d",
            "items": [
                {"symbol": "QQQ", "group": "macro_tech", "label": "纳斯达克科技", "status": "ok", "change_pct": -2.0, "bars": [{"close": 100.0}, {"close": 98.0}]},
                {"symbol": "SMH", "group": "semiconductor", "label": "半导体 ETF", "status": "ok", "change_pct": -3.0, "bars": [{"close": 100.0}, {"close": 97.0}]},
            ],
        },
        peer_history={},
        analyst_actions={},
        earnings_guidance={},
        macro_context={},
    )


def _enhanced_task_executor(tasks, run):
    task_types = {task.task_type for task in tasks}
    assert {"fetch_peer_history", "fetch_analyst_actions", "fetch_earnings_guidance", "fetch_macro_context"}.issubset(task_types)
    return [
        EvidenceTaskResult(
            task_type="fetch_peer_history",
            status="completed",
            tool_result_slot="peer_history",
            payload={
                "period": "5d",
                "items": [
                    {"symbol": "WDC", "group": "memory_storage", "label": "存储同行", "status": "ok", "change_pct": -4.2, "bars": [{"close": 100.0}, {"close": 95.8}]},
                    {"symbol": "STX", "group": "memory_storage", "label": "存储同行", "status": "ok", "change_pct": -3.8, "bars": [{"close": 100.0}, {"close": 96.2}]},
                ],
            },
        ),
        EvidenceTaskResult(
            task_type="fetch_analyst_actions",
            status="completed",
            tool_result_slot="analyst_actions",
            payload={"items": [{"firm": "Fixture Research", "action": "target_raised", "detail": "目标价上调但提示高预期波动"}]},
        ),
        EvidenceTaskResult(
            task_type="fetch_earnings_guidance",
            status="completed",
            tool_result_slot="earnings_guidance",
            payload={"items": [{"metric": "revenue_guidance", "detail": "收入指引仍强，但市场担心预期过满"}]},
        ),
        EvidenceTaskResult(
            task_type="fetch_macro_context",
            status="completed",
            tool_result_slot="macro_context",
            payload={"items": [{"metric": "nasdaq_risk", "change_pct": -2.0, "detail": "科技风险偏好回落"}]},
        ),
    ]


def test_enhanced_loop_shows_before_after_quality_improvement() -> None:
    result = build_research_run_with_loop_from_bundle(
        QUERY,
        _base_bundle_missing_peer_and_enhanced(),
        understanding=understand_query(QUERY),
        task_executor=_enhanced_task_executor,
        max_loops=1,
        research_depth="enhanced",
    )

    initial_types = {fact.fact_type for fact in result.initial_run.verified_facts}
    final_types = {fact.fact_type for fact in result.final_run.verified_facts}

    assert result.initial_run.run_id != result.final_run.run_id
    assert "peer_moves" not in initial_types
    assert {"peer_moves", "analyst_actions", "earnings_or_guidance", "macro_context"}.issubset(final_types)
    assert result.quality_delta["added_fact_types"] == ["analyst_actions", "earnings_or_guidance", "macro_context", "peer_moves"]
    assert result.quality_delta["before_attribution_level"] == "candidate_factor"
    assert result.quality_delta["after_attribution_level"] == "likely_factor"
    assert result.final_run.final_output is not None
    assert "公司研究增强" in result.final_run.final_output
    assert "分析师动作" in result.final_run.final_output
    assert "财报/指引" in result.final_run.final_output
    assert "宏观背景" in result.final_run.final_output

    comparison = render_loop_comparison(result)

    assert "## Loop 效果对比" in comparison
    assert "candidate_factor -> likely_factor" in comparison
    assert "新增证据：分析师动作、财报/指引、宏观背景、同行走势" in comparison
    assert "这说明报告不再只依赖价格和新闻标题" in comparison
    assert "归因等级变化：候选因素 -> 较可能因素" in comparison
    assert "这说明系统从“有线索但证据不足”升级到“已有同窗口对照支持”" in comparison
    assert "证据覆盖：5 类 -> 9 类" in comparison
    assert "这说明 run_1 的判断覆盖了公司、行业和宏观三层背景" in comparison


def test_loop_comparison_explains_when_live_loop_adds_no_evidence() -> None:
    result = build_research_run_with_loop_from_bundle(
        QUERY,
        _base_bundle_missing_peer_and_enhanced(),
        understanding=understand_query(QUERY),
        task_executor=lambda tasks, run: [EvidenceTaskResult(task.task_type, "skipped") for task in tasks],
        max_loops=1,
        research_depth="enhanced",
    )

    comparison = render_loop_comparison(result)

    assert "新增证据：无" in comparison
    assert "本轮 loop 没有拿到新的可核验证据" in comparison
    assert "加入了同行走势、分析师动作、财报/指引和宏观背景" not in comparison
