from src.research.models import AttributionCause, Fact, MissingFact, ResearchRunState, VerifiedFact
from src.research.report_narrative import build_report_narrative


def test_primary_cause_matches_attribution_primary_cause() -> None:
    run = ResearchRunState.start("美光 MU 最近为什么大跌？")
    run.attribution_causes = [
        AttributionCause(
            label="板块/同行同步波动",
            level="likely_factor",
            confidence="medium",
            support_fact_ids=["vf_price", "vf_peer"],
        )
    ]
    run.verified_facts = [
        VerifiedFact("vf_price", "price_move", "MU 下跌 6%。", ["src_quote"], "2026-06-28"),
        VerifiedFact("vf_peer", "peer_moves", "同行同步下跌。", ["src_peer"], "2026-06-28"),
    ]

    narrative = build_report_narrative(run)

    assert narrative.primary_cause.label == "板块/同行同步波动"
    assert narrative.primary_cause.attribution_level == "likely_factor"
    assert narrative.primary_cause.supporting_fact_types == ["price_move", "peer_moves"]


def test_remaining_gaps_include_missing_facts_and_attribution_gaps() -> None:
    run = ResearchRunState.start("美光 MU 最近为什么大跌？")
    run.missing_facts = [MissingFact("analyst_actions", "核验评级或目标价变化。", required=False)]
    run.attribution_causes = [
        AttributionCause(
            label="短期价格与新闻线索",
            level="candidate_factor",
            confidence="low",
            support_fact_ids=[],
            missing_fact_types=["macro_context"],
        )
    ]

    narrative = build_report_narrative(run)

    assert "核验评级或目标价变化。" in narrative.remaining_gaps
    assert "macro_context" in " ".join(narrative.remaining_gaps)
    assert "候选因素" in narrative.one_line_conclusion



def test_drop_query_with_positive_price_snapshot_challenges_the_premise() -> None:
    run = ResearchRunState.start("美光 MU 最近为什么大跌？")
    run.facts = [
        Fact(
            id="fact_quote",
            text="MU quote snapshot.",
            source_ids=["src_quote"],
            observed_at="2026-06-28",
            metric="latest_price",
            value={"symbol": "MU", "price": 182.5, "currency": "USD", "change_pct": 1.78},
            symbol="MU",
        )
    ]

    narrative = build_report_narrative(run)

    assert "不支持“最近大跌”" in narrative.one_line_conclusion
    assert narrative.primary_cause.label == "暂不做下跌归因"


def test_secondary_causes_deduplicate_repeated_news_event_types() -> None:
    from src.research.models import Fact

    run = ResearchRunState.start("美光 MU 最近为什么大跌？")
    run.facts = [
        Fact(
            id="fact_news",
            text="Recent news snapshot.",
            source_ids=["src_news"],
            observed_at="2026-06-28",
            metric="news_tone",
            value={
                "items": [
                    {"title": "Micron Stock Falls After Memory Rivals SK Hynix and Samsung Sink"},
                    {"title": "AI Memory Demand Linked to Nvidia Keeps Investors Focused"},
                    {"title": "Nvidia Data Center Demand Supports AI Memory Stocks"},
                    {"title": "Analyst Downgrades Micron and Cuts Price Target"},
                ]
            },
        )
    ]
    run.attribution_causes = [
        AttributionCause(
            label="短期价格与新闻线索",
            level="candidate_factor",
            confidence="low",
            support_fact_ids=[],
        )
    ]

    narrative = build_report_narrative(run)

    labels = [cause.label for cause in narrative.secondary_causes]
    assert labels.count("AI 交易预期波动") == 1
