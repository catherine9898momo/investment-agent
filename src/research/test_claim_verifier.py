from src.research.claim_verifier import filter_synthesis_to_verified_claims, verify_synthesis_claims
from src.research.context_builder import build_research_context
from src.research.models import Fact, MissingFact, ResearchRunState, Source, VerifiedFact
from src.research.synthesizer import CandidateClaim, SynthesisResult


def _run_with_price_context() -> ResearchRunState:
    run = ResearchRunState.start("美光最近为什么大跌？")
    source = Source("src_quote", "tool_result", "quote", "2026-06-07T00:00:00+00:00", tool_name="finance.get_quote")
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
        )
    ]
    run.missing_facts = [MissingFact("sector_move", "需要比较板块走势。", True)]
    run.research_context = build_research_context(run)
    return run


def test_claim_verifier_blocks_unknown_fact_ids_without_turning_them_into_missing_facts() -> None:
    run = _run_with_price_context()
    synthesis = SynthesisResult(
        claims=[CandidateClaim("MU declined because of guidance pressure.", "supporting_factor", ["fact_guidance"])],
    )

    verification = verify_synthesis_claims(run, synthesis)
    filtered = filter_synthesis_to_verified_claims(synthesis, verification)

    assert verification.passed is False
    assert verification.issues[0].issue_type == "unsupported_fact_id"
    assert verification.issues[0].retrieval_needed is True
    assert run.missing_facts[0].fact_type == "sector_move"
    assert filtered.claims == []


def test_claim_verifier_flags_price_only_causal_inference_as_retrieval_need() -> None:
    run = _run_with_price_context()
    synthesis = SynthesisResult(
        claims=[CandidateClaim("MU 下跌的原因是短期价格走弱。", "supporting_factor", ["fact_price"])],
    )

    verification = verify_synthesis_claims(run, synthesis)
    filtered = filter_synthesis_to_verified_claims(synthesis, verification)

    assert verification.passed is True
    assert verification.issues[0].issue_type == "price_only_causal_inference"
    assert verification.issues[0].retrieval_needed is True
    assert len(filtered.claims) == 1


def test_claim_verifier_blocks_direct_trading_advice_even_with_valid_fact_id() -> None:
    run = _run_with_price_context()
    synthesis = SynthesisResult(
        claims=[CandidateClaim("现在应该卖出 MU。", "supporting_factor", ["fact_price"])],
    )

    verification = verify_synthesis_claims(run, synthesis)
    filtered = filter_synthesis_to_verified_claims(synthesis, verification)

    assert verification.passed is False
    assert any(issue.issue_type == "direct_trading_advice" for issue in verification.issues)
    assert filtered.claims == []
