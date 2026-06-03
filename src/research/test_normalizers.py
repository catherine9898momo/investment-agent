from src.research.normalizers import normalize_quote, normalize_tool_result_bundle
from src.research.tool_provider import ToolResultBundle


def test_bundle_normalization_preserves_stable_metrics() -> None:
    bundle = ToolResultBundle(
        data_source="fixture",
        preferences={"style": "research first"},
        quote={"symbol": "TSLA", "price": 182.5, "currency": "USD", "change_pct": 1.7},
        history={"symbol": "TSLA", "period": "5d", "bars": [{"close": 180.0}, {"close": 182.5}]},
        news={"query": "Tesla", "items": [{"title": "mixed delivery discussion"}]},
        corporate_actions={"symbol": "TSLA", "splits_count": 2, "cumulative_split_factor": 15.0, "source": "fixture"},
    )

    normalized = normalize_tool_result_bundle(bundle, "TSLA")

    assert len(normalized.sources) == 5
    assert len(normalized.facts) == 5
    assert {fact.metric for fact in normalized.facts} == {
        "investment_preferences",
        "latest_price",
        "five_day_close_range",
        "news_tone",
        "corporate_actions",
    }
    assert all(fact.source_ids for fact in normalized.facts)


def test_tool_error_normalizes_to_failure_fact() -> None:
    normalized = normalize_quote({"error": "upstream unavailable"}, "live", "TSLA")

    assert len(normalized.sources) == 1
    assert len(normalized.facts) == 1
    fact = normalized.facts[0]
    assert fact.metric == "failure_latest_price"
    assert "failure" in fact.text
    assert fact.source_ids == [normalized.sources[0].id]
