from src.research.attribution_evaluator import evaluate_attribution_causes
from src.research.models import MissingFact, ResearchRunState, VerifiedFact


def _run_with_facts(*facts: VerifiedFact) -> ResearchRunState:
    run = ResearchRunState.start("MU 最近为什么大跌？")
    run.verified_facts = list(facts)
    return run


def _vfact(fact_type: str, raw_id: str, value: dict) -> VerifiedFact:
    return VerifiedFact(
        id=f"v_{raw_id}",
        fact_type=fact_type,
        text=f"{fact_type} fact",
        source_ids=["src"],
        observed_at="2026-06-27T00:00:00+00:00",
        raw_fact_id=raw_id,
        value=value,
    )


def test_price_and_news_only_stays_candidate_factor() -> None:
    run = _run_with_facts(
        _vfact("price_move", "fact_price", {"change_pct": -6.5}),
        _vfact("news_events", "fact_news", {"items": [{"title": "Micron shares fall on demand concerns"}]}),
    )
    run.missing_facts = [MissingFact("sector_move", "缺少板块对照。"), MissingFact("peer_moves", "缺少同行对照。")]

    causes = evaluate_attribution_causes(run)

    assert causes[0].level == "candidate_factor"
    assert {"sector_move", "peer_moves"}.issubset(set(causes[0].missing_fact_types))


def test_sector_and_peer_coverage_supports_likely_factor_with_partial_failures() -> None:
    run = _run_with_facts(
        _vfact("price_move", "fact_price", {"change_pct": -6.5}),
        _vfact("news_events", "fact_news", {"items": [{"title": "chip sector sells off"}]}),
        _vfact("sector_move", "fact_sector", {"success_count": 2, "failure_count": 1, "items": [{"symbol": "SMH", "change_pct": -2.1}, {"symbol": "QQQ", "change_pct": -1.2}]}),
        _vfact("peer_moves", "fact_peer", {"success_count": 3, "failure_count": 1, "items": [{"symbol": "NVDA", "change_pct": -1.4}, {"symbol": "WDC", "change_pct": -4.2}, {"symbol": "STX", "change_pct": -3.8}]}),
    )

    causes = evaluate_attribution_causes(run)

    assert causes[0].level == "likely_factor"
    assert causes[0].confidence == "medium"
    assert "partial" in causes[0].rationale.lower()


def test_sector_peer_all_failed_downgrades_to_candidate() -> None:
    run = _run_with_facts(
        _vfact("price_move", "fact_price", {"change_pct": -6.5}),
        _vfact("sector_move", "fact_sector", {"success_count": 0, "failure_count": 3, "items": []}),
        _vfact("peer_moves", "fact_peer", {"success_count": 0, "failure_count": 5, "items": []}),
    )

    causes = evaluate_attribution_causes(run)

    assert causes[0].level == "candidate_factor"
    assert "coverage" in causes[0].rationale.lower()
