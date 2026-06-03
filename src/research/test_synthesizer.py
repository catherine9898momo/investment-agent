from src.research.models import Fact, ResearchRunState, Source
from src.research.synthesizer import (
    RESEARCH_SYNTHESIS_SCHEMA,
    MockLLMResearchSynthesizer,
    bind_claims_to_evidence,
    synthesis_result_from_data,
)


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


def test_research_synthesis_schema_requires_strict_claim_shape() -> None:
    assert RESEARCH_SYNTHESIS_SCHEMA["required"] == ["claims", "human_confirmation_points"]
    assert RESEARCH_SYNTHESIS_SCHEMA["additionalProperties"] is False
    claim_schema = RESEARCH_SYNTHESIS_SCHEMA["properties"]["claims"]["items"]
    assert claim_schema["required"] == ["text", "claim_type", "fact_ids", "is_key"]
    assert claim_schema["additionalProperties"] is False
    assert "risk_factor" in claim_schema["properties"]["claim_type"]["enum"]


def test_synthesis_result_from_structured_data() -> None:
    result = synthesis_result_from_data(
        {
            "claims": [
                {
                    "text": "News evidence remains mixed.",
                    "claim_type": "risk_factor",
                    "fact_ids": ["fact_news"],
                    "is_key": True,
                }
            ],
            "human_confirmation_points": ["Confirm source freshness."],
        },
        raw="raw-json",
    )

    assert len(result.claims) == 1
    assert result.claims[0].claim_type == "risk_factor"
    assert result.claims[0].fact_ids == ["fact_news"]
    assert result.human_confirmation_points == ["Confirm source freshness."]
    assert result.raw_model_output == "raw-json"


def test_synthesis_result_filters_incomplete_claim_text() -> None:
    result = synthesis_result_from_data(
        {
            "claims": [
                {
                    "text": "Tesla was reported to have added",
                    "claim_type": "risk_factor",
                    "fact_ids": ["fact_news"],
                    "is_key": True,
                },
                {
                    "text": "Competition pressure remains a risk signal.",
                    "claim_type": "risk_factor",
                    "fact_ids": ["fact_news"],
                    "is_key": True,
                },
            ],
            "human_confirmation_points": [],
        }
    )

    assert len(result.claims) == 1
    assert result.claims[0].text == "Competition pressure remains a risk signal."


def test_mock_synthesizer_turns_data_quality_facts_into_limited_claims() -> None:
    run = ResearchRunState.start("TSLA 数据质量如何？")
    source = Source(
        id="src_quality",
        kind="tool_result",
        name="data quality",
        tool_name="research.data_quality_check",
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
        Fact(
            id="fact_stale",
            text="Data quality limitation for TSLA: quote timestamp is stale.",
            source_ids=[source.id],
            observed_at=source.fetched_at,
            metric="stale_quote",
        ),
        Fact(
            id="fact_missing",
            text="Data quality limitation for TSLA: news results are missing.",
            source_ids=[source.id],
            observed_at=source.fetched_at,
            metric="missing_news",
        ),
    ])

    synthesis = MockLLMResearchSynthesizer().synthesize(run)
    claims = bind_claims_to_evidence(run, synthesis)

    quality_claims = [claim for claim in claims if "Data quality limitation" in claim.text]
    assert {claim.claim_type for claim in quality_claims} == {"risk_factor", "unknown"}
    assert all(claim.evidence for claim in quality_claims)
    assert any("stale" in point for point in synthesis.human_confirmation_points)
