from src.research.evidence_tasks import EvidenceTaskResult, merge_task_results_into_bundle
from src.research.tool_provider import ToolResultBundle


def _bundle() -> ToolResultBundle:
    return ToolResultBundle(
        data_source="fixture",
        preferences={"style": "value"},
        quote={"symbol": "MU", "price": 100.0},
        history={"symbol": "MU", "bars": [{"close": 100.0}]},
        news={"query": "Micron", "items": []},
        corporate_actions={"symbol": "MU", "actions": []},
        sector_history={},
        peer_history={},
    )


def test_retry_news_zh_result_replaces_empty_news_slot() -> None:
    base = _bundle()
    zh_news = {"query": "美光", "items": [{"title": "美光新闻"}]}

    enhanced = merge_task_results_into_bundle(
        base,
        [EvidenceTaskResult("retry_news_zh", "completed", "news", zh_news)],
    )

    assert enhanced.news == zh_news
    assert enhanced.quote == base.quote


def test_fetch_peer_history_result_adds_peer_history_slot() -> None:
    base = _bundle()
    peer_history = {
        "period": "5d",
        "items": [{"symbol": "NVDA", "status": "ok", "change_pct": -2.3, "bars": [{"close": 10.0}, {"close": 9.77}]}],
    }

    enhanced = merge_task_results_into_bundle(
        base,
        [EvidenceTaskResult("fetch_peer_history", "completed", "peer_history", peer_history)],
    )

    assert enhanced.peer_history == peer_history
    assert enhanced.sector_history == {}


def test_failed_task_result_does_not_mutate_bundle() -> None:
    base = _bundle()

    enhanced = merge_task_results_into_bundle(
        base,
        [EvidenceTaskResult("fetch_peer_history", "failed", "peer_history", {"items": [{"symbol": "NVDA"}]}, "timeout")],
    )

    assert enhanced == base
    assert enhanced.peer_history == {}


def test_merge_is_pure_function() -> None:
    base = _bundle()
    original_news = base.news
    original_peer_history = base.peer_history

    enhanced = merge_task_results_into_bundle(
        base,
        [
            EvidenceTaskResult("retry_news_zh", "completed", "news", {"query": "美光", "items": [{"title": "新新闻"}]}),
            EvidenceTaskResult("fetch_peer_history", "completed", "peer_history", {"period": "5d", "items": []}),
        ],
    )

    assert base.news is original_news
    assert base.peer_history is original_peer_history
    assert base.news == {"query": "Micron", "items": []}
    assert base.peer_history == {}
    assert enhanced is not base
