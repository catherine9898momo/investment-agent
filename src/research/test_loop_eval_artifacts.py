import json
from pathlib import Path

from src.research.evidence_tasks import EvidenceTaskResult
from src.research.loop_engine import build_research_run_with_loop_from_bundle
from src.research.loop_eval_artifacts import save_loop_eval_artifact
from src.research.query_intake import understand_query
from src.research.test_loop_enhanced_company_report import QUERY, _base_bundle_missing_peer_and_enhanced, _enhanced_task_executor


def test_save_loop_eval_artifact_writes_before_after_compare_and_metrics(tmp_path: Path) -> None:
    result = build_research_run_with_loop_from_bundle(
        QUERY,
        _base_bundle_missing_peer_and_enhanced(),
        understanding=understand_query(QUERY),
        task_executor=_enhanced_task_executor,
        max_loops=1,
        research_depth="enhanced",
    )

    artifact_dir = save_loop_eval_artifact(result, tmp_path, query=QUERY, data_source="fixture")

    assert (artifact_dir / "run_0_report.md").exists()
    assert (artifact_dir / "run_1_report.md").exists()
    assert (artifact_dir / "loop_compare.md").exists()
    metrics = json.loads((artifact_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["improvement"]["added_evidence"] == ["analyst_actions", "earnings_or_guidance", "macro_context", "peer_moves"]
    assert metrics["before"]["attribution_level"] == "candidate_factor"
    assert metrics["after"]["attribution_level"] == "likely_factor"
    assert metrics["stop_decision"]["stop_reason"] == result.stop_reason
    assert metrics["stop_decision"]["quality_status"] == result.stop_decision.quality_status
    assert metrics["stop_decision"]["user_message"]
    assert metrics["stop_decision"]["should_continue"] is False
    assert metrics["stop_decision"]["can_continue"] is False
