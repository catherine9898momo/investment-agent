from src.research.evidence_tasks import EvidenceTaskPlanner
from src.research.models import ResearchRunState, ResolvedEntity
from src.research.quality_auditor import QualityIssue


def _run(symbol: str = "MU") -> ResearchRunState:
    run = ResearchRunState.start("美光 MU 最近为什么大跌？")
    run.resolved_entity = ResolvedEntity("MU", symbol, "Micron")
    return run


def _issue(issue_type: str, *, retrieval_needed: bool = True, suggested_task_type: str | None = None) -> QualityIssue:
    return QualityIssue(
        issue_type=issue_type,
        severity="warning",
        message=f"{issue_type} issue",
        affected_fact_types=[],
        retrieval_needed=retrieval_needed,
        suggested_task_type=suggested_task_type,
    )


def test_planner_maps_partial_news_to_retry_news_zh() -> None:
    tasks = EvidenceTaskPlanner().plan(
        [_issue("partial_news_events", suggested_task_type="retry_news_zh")],
        _run("600519.SS"),
    )

    assert len(tasks) == 1
    assert tasks[0].task_type == "retry_news_zh"
    assert tasks[0].target_symbol == "600519.SS"
    assert tasks[0].required_fact_type == "news_events"
    assert tasks[0].max_attempts == 1


def test_planner_maps_missing_peer_moves_to_fetch_peer_history() -> None:
    tasks = EvidenceTaskPlanner().plan(
        [_issue("missing_peer_moves", suggested_task_type="fetch_peer_history")],
        _run(),
    )

    assert len(tasks) == 1
    assert tasks[0].task_type == "fetch_peer_history"
    assert tasks[0].required_fact_type == "peer_moves"


def test_planner_maps_missing_sector_move_to_fetch_sector_history() -> None:
    tasks = EvidenceTaskPlanner().plan(
        [_issue("missing_sector_move", suggested_task_type="fetch_sector_history")],
        _run(),
    )

    assert len(tasks) == 1
    assert tasks[0].task_type == "fetch_sector_history"
    assert tasks[0].required_fact_type == "sector_move"


def test_planner_maps_overstated_attribution_to_rerender_with_downgrade() -> None:
    tasks = EvidenceTaskPlanner().plan(
        [_issue(
            "partial_comparison_supports_likely_factor",
            retrieval_needed=False,
            suggested_task_type="rerender_with_downgrade",
        )],
        _run(),
    )

    assert len(tasks) == 1
    assert tasks[0].task_type == "rerender_with_downgrade"
    assert tasks[0].required_fact_type is None


def test_planner_ignores_unknown_issue_types() -> None:
    tasks = EvidenceTaskPlanner().plan([_issue("semantic_support_weak")], _run())

    assert tasks == []


def test_planner_deduplicates_duplicate_task_types() -> None:
    tasks = EvidenceTaskPlanner().plan(
        [
            _issue("missing_peer_moves", suggested_task_type="fetch_peer_history"),
            _issue("missing_peer_moves", suggested_task_type="fetch_peer_history"),
        ],
        _run(),
    )

    assert len(tasks) == 1
    assert tasks[0].task_type == "fetch_peer_history"
