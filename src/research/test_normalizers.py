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


def test_bundle_normalization_adds_stale_quote_quality_fact() -> None:
    bundle = ToolResultBundle(
        data_source="fixture",
        preferences={"style": "research first"},
        quote={"symbol": "TSLA", "price": 182.5, "currency": "USD", "change_pct": 1.7, "as_of": "2026-05-15T12:00:00+00:00"},
        history={"symbol": "TSLA", "period": "5d", "bars": [{"close": 180.0}, {"close": 182.5}]},
        news={"query": "Tesla", "items": [{"title": "mixed delivery discussion"}]},
        corporate_actions={"symbol": "TSLA", "splits_count": 2, "cumulative_split_factor": 15.0, "source": "fixture"},
    )

    normalized = normalize_tool_result_bundle(bundle, "TSLA")

    assert "stale_quote" in {fact.metric for fact in normalized.facts}
    stale_fact = next(fact for fact in normalized.facts if fact.metric == "stale_quote")
    assert "stale" in stale_fact.text


def test_bundle_normalization_adds_missing_news_quality_fact() -> None:
    bundle = ToolResultBundle(
        data_source="fixture",
        preferences={"style": "research first"},
        quote={"symbol": "TSLA", "price": 182.5, "currency": "USD", "change_pct": 1.7},
        history={"symbol": "TSLA", "period": "5d", "bars": [{"close": 180.0}, {"close": 182.5}]},
        news={"query": "Tesla", "items": []},
        corporate_actions={"symbol": "TSLA", "splits_count": 2, "cumulative_split_factor": 15.0, "source": "fixture"},
    )

    normalized = normalize_tool_result_bundle(bundle, "TSLA")

    assert {"unknown_news", "missing_news"}.issubset({fact.metric for fact in normalized.facts})


def test_bundle_normalization_adds_conflicting_signals_quality_fact() -> None:
    bundle = ToolResultBundle(
        data_source="fixture",
        preferences={"style": "research first"},
        quote={"symbol": "TSLA", "price": 182.5, "currency": "USD", "change_pct": 1.7},
        history={"symbol": "TSLA", "period": "5d", "bars": [{"close": 190.0}, {"close": 170.0}]},
        news={"query": "Tesla", "items": [{"title": "Tesla deliveries beat expectations and shares rally"}]},
        corporate_actions={"symbol": "TSLA", "splits_count": 2, "cumulative_split_factor": 15.0, "source": "fixture"},
    )

    normalized = normalize_tool_result_bundle(bundle, "TSLA")

    conflict_fact = next(fact for fact in normalized.facts if fact.metric == "conflicting_signals")
    assert "conflicts" in conflict_fact.text
