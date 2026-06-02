from src.research.models import Fact, ResearchRunState, Source
from src.research.synthesizer import MockLLMResearchSynthesizer, bind_claims_to_evidence


def test_mock_synthesizer_outputs_claims_with_evidence_after_binding() -> None:
    run = ResearchRunState.start("帮我看 TSLA 是否值得继续关注。")
    source = Source(
        id="src_quote",
        kind="tool_result",
        name="quote",
        tool_name="finance.get_quote",
        fetched_at="2026-06-01T12:00:00+00:00",
    )
    run.sources.append(source)
    run.facts.extend([
        Fact(
            id="fact_price",
            text="TSLA quote snapshot.",
            source_ids=[source.id],
            observed_at=source.fetched_at,
            metric="latest_price",
        ),
        Fact(
            id="fact_news",
            text="TSLA news is mixed.",
            source_ids=[source.id],
            observed_at=source.fetched_at,
            metric="news_tone",
        ),
        Fact(
            id="fact_pref",
            text="User prefers value-investing research.",
            source_ids=[source.id],
            observed_at=source.fetched_at,
            metric="investment_preferences",
        ),
        Fact(
            id="fact_history",
            text="Short-term price history is not enough.",
            source_ids=[source.id],
            observed_at=source.fetched_at,
            metric="five_day_close_range",
        ),
    ])

    synthesis = MockLLMResearchSynthesizer().synthesize(run)
    claims = bind_claims_to_evidence(run, synthesis)

    assert len(claims) == 4
    assert all(claim.evidence for claim in claims)
    assert synthesis.human_confirmation_points
