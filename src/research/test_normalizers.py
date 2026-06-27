from src.research.normalizers import normalize_quote, normalize_tool_result_bundle
from src.research.tool_provider import ToolResultBundle


def test_bundle_normalization_preserves_stable_metrics() -> None:
    bundle = ToolResultBundle(
        data_source="fixture",
        preferences={"style": "research first"},
        quote={"symbol": "TSLA", "price": 182.5, "currency": "USD", "change_pct": 1.7},
        history={"symbol": "TSLA", "period": "5d", "bars": [{"close": 178.0}, {"close": 179.0}, {"close": 180.0}, {"close": 181.0}, {"close": 182.5}]},
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



def test_history_with_one_valid_close_is_not_promoted_to_price_range() -> None:
    bundle = ToolResultBundle(
        data_source="fixture",
        preferences={"style": "research first"},
        quote={"symbol": "MU", "price": 85.0, "previous_close": 86.0, "change_pct": -1.16, "currency": "USD"},
        history={
            "symbol": "MU",
            "period": "5d",
            "bars": [
                {"date": "2026-06-01", "close": float("nan")},
                {"date": "2026-06-02", "close": None},
                {"date": "2026-06-03", "close": 85.0},
            ],
        },
        news={"query": "Micron", "items": [{"title": "Micron shares fall"}]},
        corporate_actions={"symbol": "MU", "actions": [], "splits_count": 0, "cumulative_split_factor": 1.0, "source": "fixture"},
    )

    normalized = normalize_tool_result_bundle(bundle, "MU")
    metrics = {fact.metric for fact in normalized.facts}

    assert "five_day_close_range" not in metrics
    assert "data_quality_history_insufficient" in metrics


def test_history_with_two_valid_closes_gets_range_and_window_warning() -> None:
    bundle = ToolResultBundle(
        data_source="fixture",
        preferences={"style": "research first"},
        quote={"symbol": "MU", "price": 85.0, "previous_close": 86.0, "change_pct": -1.16, "currency": "USD"},
        history={
            "symbol": "MU",
            "period": "5d",
            "bars": [
                {"date": "2026-06-01", "close": 92.0},
                {"date": "2026-06-02", "close": None},
                {"date": "2026-06-03", "close": 85.0},
            ],
        },
        news={"query": "Micron", "items": [{"title": "Micron shares fall"}]},
        corporate_actions={"symbol": "MU", "actions": [], "splits_count": 0, "cumulative_split_factor": 1.0, "source": "fixture"},
    )

    normalized = normalize_tool_result_bundle(bundle, "MU")
    metrics = {fact.metric for fact in normalized.facts}

    assert "five_day_close_range" in metrics
    assert "data_quality_history_window_incomplete" in metrics


def test_quote_validation_flags_invalid_numbers_and_change_mismatch() -> None:
    bundle = ToolResultBundle(
        data_source="fixture",
        preferences={"style": "research first"},
        quote={"symbol": "MU", "price": 110.0, "previous_close": 100.0, "change_pct": 2.0, "currency": "USD"},
        history={"symbol": "MU", "period": "5d", "bars": [{"close": 100.0}, {"close": 110.0}, {"close": 111.0}, {"close": 112.0}, {"close": 113.0}]},
        news={"query": "Micron", "items": [{"title": "Micron shares rise"}]},
        corporate_actions={"symbol": "MU", "actions": [], "splits_count": 0, "cumulative_split_factor": 1.0, "source": "fixture"},
    )

    normalized = normalize_tool_result_bundle(bundle, "MU")

    assert "data_quality_quote_change_mismatch" in {fact.metric for fact in normalized.facts}


def test_corporate_action_in_window_with_unknown_adjustment_metadata_adds_quality_fact() -> None:
    bundle = ToolResultBundle(
        data_source="fixture",
        preferences={"style": "research first"},
        quote={"symbol": "MU", "price": 85.0, "previous_close": 86.0, "change_pct": -1.16, "currency": "USD"},
        history={"symbol": "MU", "period": "5d", "bars": [{"date": "2026-06-01", "close": 92.0}, {"date": "2026-06-05", "close": 85.0}]},
        news={"query": "Micron", "items": [{"title": "Micron shares fall"}]},
        corporate_actions={
            "symbol": "MU",
            "actions": [{"action_type": "split", "date": "2026-06-03", "ratio": "2:1", "factor": 2.0}],
            "splits_count": 1,
            "cumulative_split_factor": 2.0,
            "source": "fixture",
        },
    )

    normalized = normalize_tool_result_bundle(bundle, "MU")

    assert "data_quality_corporate_action_adjustment_uncertain" in {fact.metric for fact in normalized.facts}


def test_abnormal_quote_vs_history_emits_uncertain_provenance() -> None:
    bundle = ToolResultBundle(
        data_source="fixture",
        preferences={"style": "research first"},
        quote={"symbol": "MU", "price": 150.0, "previous_close": 149.0, "change_pct": 0.67, "currency": "USD"},
        history={"symbol": "MU", "period": "5d", "bars": [{"close": 80.0}, {"close": 82.0}, {"close": 81.0}, {"close": 83.0}, {"close": 84.0}]},
        news={"query": "Micron", "items": [{"title": "Micron shares move on demand concerns"}]},
        corporate_actions={"symbol": "MU", "actions": [], "splits_count": 0, "cumulative_split_factor": 1.0, "source": "fixture"},
    )

    normalized = normalize_tool_result_bundle(bundle, "MU")

    assert "price_provenance_uncertain" in {fact.metric for fact in normalized.facts}


def test_bundle_normalization_adds_sector_and_peer_move_facts_with_partial_failures() -> None:
    bundle = ToolResultBundle(
        data_source="fixture",
        preferences={"style": "research first"},
        quote={"symbol": "MU", "price": 85.0, "previous_close": 91.0, "change_pct": -6.59, "currency": "USD"},
        history={"symbol": "MU", "period": "5d", "bars": [{"close": 91.0}, {"close": 90.0}, {"close": 88.0}, {"close": 86.0}, {"close": 85.0}]},
        news={"query": "Micron", "items": [{"title": "chip sector sells off"}]},
        corporate_actions={"symbol": "MU", "actions": [], "splits_count": 0, "cumulative_split_factor": 1.0, "source": "fixture"},
        sector_history={
            "items": [
                {"symbol": "SMH", "group": "semiconductor", "status": "ok", "change_pct": -2.1, "bars": [{"close": 100}, {"close": 97.9}]},
                {"symbol": "SOXX", "group": "semiconductor", "status": "error", "error": "upstream timeout"},
                {"symbol": "QQQ", "group": "macro_tech", "status": "ok", "change_pct": -1.1, "bars": [{"close": 100}, {"close": 98.9}]},
            ]
        },
        peer_history={
            "items": [
                {"symbol": "NVDA", "group": "ai_semiconductor", "status": "ok", "change_pct": -1.4, "bars": [{"close": 100}, {"close": 98.6}]},
                {"symbol": "WDC", "group": "memory_storage", "status": "ok", "change_pct": -4.2, "bars": [{"close": 100}, {"close": 95.8}]},
                {"symbol": "STX", "group": "memory_storage", "status": "error", "error": "upstream timeout"},
            ]
        },
    )

    normalized = normalize_tool_result_bundle(bundle, "MU")
    metrics = {fact.metric for fact in normalized.facts}
    sector = next(fact for fact in normalized.facts if fact.metric == "sector_move")
    peers = next(fact for fact in normalized.facts if fact.metric == "peer_moves")

    assert {"sector_move", "peer_moves", "data_quality_sector_peer_partial"}.issubset(metrics)
    assert sector.value["success_count"] == 2
    assert sector.value["failure_count"] == 1
    assert peers.value["success_count"] == 2
    assert peers.value["failure_count"] == 1
