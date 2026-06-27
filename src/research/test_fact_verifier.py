from src.research.attribution_planner import build_attribution_plan
from src.research.fact_verifier import build_verified_fact_table
from src.research.models import Fact, IntentRoute, ResolvedEntity, Source, TimeWindow


def test_verified_fact_table_records_missing_attribution_needs() -> None:
    source = Source("src_quote", "tool_result", "quote", "2026-06-07T00:00:00+00:00")
    facts = [
        Fact(
            id="fact_quote",
            text="MU quote snapshot.",
            source_ids=[source.id],
            observed_at=source.fetched_at,
            metric="latest_price",
            value={"change_pct": -4.2},
            symbol="MU",
        )
    ]
    plan = build_attribution_plan(
        IntentRoute("news_explanation", "用户询问涨跌原因。"),
        ResolvedEntity("美光", "MU", "Micron"),
        TimeWindow("最近", "2026-06-01", "2026-06-07"),
        "美光最近为什么会大跌？",
    )

    verified, missing = build_verified_fact_table(facts, plan)

    assert verified[0].fact_type == "price_move"
    assert "sector_move" in {item.fact_type for item in missing}
    assert "peer_moves" in {item.fact_type for item in missing}


def test_fact_verifier_maps_sector_and_peer_moves() -> None:
    from src.research.fact_verifier import build_verified_fact_table
    from src.research.models import Fact

    facts = [
        Fact("fact_sector", "sector moved lower", ["src"], "2026-06-27T00:00:00+00:00", metric="sector_move", value={"success_count": 2}),
        Fact("fact_peer", "peers moved lower", ["src"], "2026-06-27T00:00:00+00:00", metric="peer_moves", value={"success_count": 2}),
    ]

    verified, missing = build_verified_fact_table(facts, None)

    assert [fact.fact_type for fact in verified] == ["sector_move", "peer_moves"]
    assert missing == []
