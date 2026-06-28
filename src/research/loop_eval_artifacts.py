"""Persist loop before/after reports and metrics for demos and interviews."""

from __future__ import annotations

import json
from pathlib import Path

from src.research.loop_engine import LoopResult, render_loop_comparison
from src.research.models import to_jsonable


def save_loop_eval_artifact(result: LoopResult, base_dir: Path | str, *, query: str, data_source: str) -> Path:
    base = Path(base_dir)
    symbol = result.final_run.resolved_entity.symbol if result.final_run.resolved_entity else "unknown"
    artifact_dir = base / f"{result.final_run.started_at.replace(':', '').replace('+', '_')}_{symbol}"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    comparison = render_loop_comparison(result)
    (artifact_dir / "run_0_report.md").write_text(result.initial_run.final_output or "", encoding="utf-8")
    (artifact_dir / "run_1_report.md").write_text(result.final_run.final_output or "", encoding="utf-8")
    (artifact_dir / "loop_compare.md").write_text(comparison, encoding="utf-8")
    (artifact_dir / "metrics.json").write_text(json.dumps(_metrics(result, query, data_source), ensure_ascii=False, indent=2), encoding="utf-8")
    (artifact_dir / "trace_paths.json").write_text(json.dumps({
        "initial_trace_path": result.initial_run.trace_path,
        "final_trace_path": result.final_run.trace_path,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (artifact_dir / "evidence_delta.json").write_text(json.dumps(to_jsonable(result.quality_delta), ensure_ascii=False, indent=2), encoding="utf-8")
    return artifact_dir


def _metrics(result: LoopResult, query: str, data_source: str) -> dict:
    before_types = sorted({fact.fact_type for fact in result.initial_run.verified_facts})
    after_types = sorted({fact.fact_type for fact in result.final_run.verified_facts})
    return {
        "query": query,
        "data_source": data_source,
        "before": {
            "verified_fact_types": before_types,
            "attribution_level": result.quality_delta.get("before_attribution_level"),
            "guardrail_passed": result.initial_run.guardrail.passed if result.initial_run.guardrail else None,
        },
        "after": {
            "verified_fact_types": after_types,
            "attribution_level": result.quality_delta.get("after_attribution_level"),
            "guardrail_passed": result.final_run.guardrail.passed if result.final_run.guardrail else None,
        },
        "improvement": {
            "added_evidence": result.quality_delta.get("added_fact_types") or [],
            "resolved_missing": result.quality_delta.get("resolved_missing_fact_types") or [],
            "explanation": "报告从短期归因扩展到公司研究增强层。" if result.quality_delta.get("added_fact_types") else "本轮 loop 未获得新增可核验证据。",
        },
        "stop_decision": _stop_decision_metrics(result),
    }


def _stop_decision_metrics(result: LoopResult) -> dict:
    decision = result.stop_decision
    if decision is None:
        return {
            "stop_reason": result.stop_reason,
            "quality_status": None,
            "user_message": None,
            "should_continue": None,
            "can_continue": None,
            "remaining_actionable_tasks": [],
            "remaining_gaps": result.quality_delta.get("remaining_missing_fact_types") or [],
            "improvement_summary": [],
        }
    return {
        "stop_reason": decision.stop_reason,
        "quality_status": decision.quality_status,
        "user_message": decision.user_message,
        "should_continue": decision.should_continue,
        "can_continue": decision.can_continue,
        "remaining_actionable_tasks": decision.remaining_actionable_tasks,
        "remaining_gaps": decision.remaining_gaps,
        "improvement_summary": decision.improvement_summary,
    }
