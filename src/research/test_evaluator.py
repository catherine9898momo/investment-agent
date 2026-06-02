from src.research.evaluator import evaluate_research_output
from src.research.models import Claim, Evidence, Fact, ResearchRunState, Source


def _run_with_evidence() -> ResearchRunState:
    run = ResearchRunState.start("帮我看 TSLA 最近是否还值得继续关注。")
    source = Source(
        id="src_quote",
        kind="tool_result",
        name="quote",
        tool_name="finance.get_quote",
        fetched_at="2026-06-01T12:00:00+00:00",
    )
    fact = Fact(
        id="fact_price",
        text="TSLA quote snapshot has source timestamp.",
        source_ids=[source.id],
        observed_at=source.fetched_at,
    )
    claim = Claim(
        id="claim_price",
        text="TSLA has a sourced quote snapshot.",
        evidence=[Evidence(fact_id=fact.id, source_id=source.id)],
    )
    run.sources.append(source)
    run.facts.append(fact)
    run.claims.append(claim)
    run.human_confirmation_points.append("请人工确认研究 thesis。")
    return run


def test_evaluator_passes_traceable_research_output() -> None:
    run = _run_with_evidence()
    output = (
        "来源: src_quote, 时间: 2026-06-01. "
        "这是研究摘要，不是交易指令。风险和未知项需要人工确认。"
    )

    result = evaluate_research_output(run, output)

    assert result.passed


def test_evaluator_blocks_direct_trading_advice() -> None:
    run = _run_with_evidence()
    output = "来源: src_quote, 时间: 2026-06-01. 建议买入 TSLA。风险已考虑。"

    result = evaluate_research_output(run, output)

    assert not result.passed
    assert any(check.name == "no_direct_trading_advice" and not check.passed for check in result.checks)


def test_evaluator_blocks_key_claim_without_evidence() -> None:
    run = _run_with_evidence()
    run.claims[0].evidence = []
    output = "来源: src_quote, 时间: 2026-06-01. 风险和未知项需要人工确认。"

    result = evaluate_research_output(run, output)

    assert not result.passed
    assert any(check.name == "key_claims_have_evidence" and not check.passed for check in result.checks)
