from src.research.context_builder import build_research_context, research_context_to_prompt_payload
from src.research.models import (
    AttributionNeed,
    AttributionPlan,
    Fact,
    IntentRoute,
    MissingFact,
    ResearchRunState,
    ResolvedEntity,
    Source,
    TimeWindow,
    VerifiedFact,
)
from src.research.synthesizer import build_synthesis_prompt


def _run_with_context_inputs() -> ResearchRunState:
    run = ResearchRunState.start("美光最近为什么大跌？")
    source = Source(
        id="src_quote",
        kind="tool_result",
        name="quote",
        fetched_at="2026-06-07T00:00:00+00:00",
        tool_name="finance.get_quote",
    )
    run.sources.append(source)
    run.facts.append(
        Fact(
            id="fact_price",
            text="MU declined 4.2% during the latest observed window.",
            source_ids=[source.id],
            observed_at=source.fetched_at,
            metric="latest_price",
            value={"change_pct": -4.2},
            symbol="MU",
        )
    )
    run.resolved_entity = ResolvedEntity("美光", "MU", "Micron", "Micron Technology, Inc.", "high")
    run.intent_route = IntentRoute("news_explanation", "用户主要在询问涨跌原因。")
    run.time_window = TimeWindow("最近 5 个交易日", "2026-06-01", "2026-06-07", "medium", "默认短期归因窗口。")
    run.attribution_plan = AttributionPlan(
        "price_drop",
        [AttributionNeed("price_move", "确认价格变化。"), AttributionNeed("sector_move", "确认板块是否同步下跌。")],
        peer_symbols=["WDC", "STX"],
        index_symbols=["SMH", "QQQ"],
    )
    run.verified_facts = [
        VerifiedFact(
            id="vfact_price",
            fact_type="price_move",
            text="MU declined 4.2% during the latest observed window.",
            source_ids=[source.id],
            observed_at=source.fetched_at,
            confidence="medium",
            verification_status="verified",
            raw_fact_id="fact_price",
            value={"change_pct": -4.2},
        ),
        VerifiedFact(
            id="vfact_pref",
            fact_type="user_preferences",
            text="User prefers value-investing research over trading advice.",
            source_ids=[source.id],
            observed_at=source.fetched_at,
            confidence="medium",
            verification_status="verified",
            raw_fact_id="fact_pref",
        ),
    ]
    run.missing_facts = [MissingFact("sector_move", "需要比较半导体板块走势。", True)]
    return run


def test_build_research_context_exposes_only_citable_verified_facts_and_missing_gaps() -> None:
    context = build_research_context(_run_with_context_inputs())

    assert context.user_query == "美光最近为什么大跌？"
    assert context.entity and context.entity.symbol == "MU"
    assert [fact.fact_id for fact in context.facts] == ["fact_price", "fact_pref"]
    assert context.user_preferences[0].fact_id == "fact_pref"
    assert context.missing_facts[0].fact_type == "sector_move"
    assert "price movement alone" in " ".join(context.unsupported_claim_constraints)
    assert context.source_ids == ["src_quote"]


def test_research_context_payload_is_prompt_serializable() -> None:
    context = build_research_context(_run_with_context_inputs())
    payload = research_context_to_prompt_payload(context)

    assert payload["entity"]["symbol"] == "MU"
    assert payload["facts"][0]["fact_id"] == "fact_price"
    assert payload["missing_facts"][0]["required"] is True


def test_synthesis_prompt_uses_research_context_instead_of_raw_fact_rows() -> None:
    run = _run_with_context_inputs()
    run.research_context = build_research_context(run)

    prompt = build_synthesis_prompt(run)

    assert "Context:" in prompt
    assert "unsupported_claim_constraints" in prompt
    assert "sector_move" in prompt
    assert "metric" not in prompt
    assert "fact_price" in prompt
