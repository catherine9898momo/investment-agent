import json
from pathlib import Path

from src.research.evidence_tasks import EvidenceTaskResult
from src.research.loop_engine import build_research_run_with_loop_from_bundle
from src.research.query_intake import understand_query
from src.research.tool_provider import ToolResultBundle


QUERY = "美光 MU 最近为什么大跌？"


def _base_bundle_without_peers() -> ToolResultBundle:
    return ToolResultBundle(
        data_source="fixture",
        preferences={"style": "价值投资研究优先"},
        quote={"symbol": "MU", "price": 94.0, "previous_close": 100.0, "change_pct": -6.0, "currency": "USD"},
        history={
            "symbol": "MU",
            "period": "5d",
            "bars": [{"date": "2026-06-24", "close": 100.0}, {"date": "2026-06-25", "close": 96.0}, {"date": "2026-06-26", "close": 94.0}],
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
    )


def _peer_task_executor(tasks, run):
    assert any(task.task_type == "fetch_peer_history" for task in tasks)
    return [
        EvidenceTaskResult(
            task_type="fetch_peer_history",
            status="completed",
            tool_result_slot="peer_history",
            payload={
                "period": "5d",
                "items": [
                    {"symbol": "NVDA", "group": "ai_semiconductor", "label": "AI 半导体", "status": "ok", "change_pct": -2.1, "bars": [{"close": 100.0}, {"close": 97.9}]},
                    {"symbol": "AMD", "group": "ai_semiconductor", "label": "AI 半导体", "status": "ok", "change_pct": -2.8, "bars": [{"close": 100.0}, {"close": 97.2}]},
                ],
            },
        )
    ]


def test_loop_rebuilds_run_1_from_enhanced_bundle() -> None:
    result = build_research_run_with_loop_from_bundle(
        QUERY,
        _base_bundle_without_peers(),
        understanding=understand_query(QUERY),
        task_executor=_peer_task_executor,
        max_loops=1,
    )

    initial_fact_types = {fact.fact_type for fact in result.initial_run.verified_facts}
    final_fact_types = {fact.fact_type for fact in result.final_run.verified_facts}

    assert result.initial_run.run_id != result.final_run.run_id
    assert "peer_moves" not in initial_fact_types
    assert "peer_moves" in final_fact_types
    assert result.quality_delta["added_fact_types"] == ["peer_moves"]


def test_loop_summary_and_trace_record_evidence_repair() -> None:
    result = build_research_run_with_loop_from_bundle(
        QUERY,
        _base_bundle_without_peers(),
        understanding=understand_query(QUERY),
        task_executor=_peer_task_executor,
        max_loops=1,
    )

    assert result.final_run.final_output is not None
    assert "## 本轮质量改进" in result.final_run.final_output
    assert "新增证据：同行走势" in result.final_run.final_output
    assert "质量状态：" in result.final_run.final_output
    assert "为什么停：" in result.final_run.final_output
    assert "是否建议继续：" in result.final_run.final_output

    trace_path = Path(result.final_run.trace_path or "")
    trace_events = [json.loads(line)["event_type"] for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert "loop_started" in trace_events
    assert "enhanced_bundle_built" in trace_events
    assert "run_rebuilt_from_enhanced_bundle" in trace_events
    assert "loop_stopped" in trace_events
