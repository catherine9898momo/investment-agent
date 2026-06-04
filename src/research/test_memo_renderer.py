from src.research.memo_renderer import build_evidence_rows, memo_trace_payload, render_investment_memo
from src.research.models import Claim, Evidence, Fact, ResearchRunState, Source


def test_render_investment_memo_includes_evidence_table_and_trace_payload() -> None:
    run = ResearchRunState.start("研究 TSLA 风险")
    source = Source(
        id="src_quote",
        kind="tool_result",
        name="live quote snapshot",
        fetched_at="2026-06-04T00:00:00+00:00",
        tool_name="finance.get_quote",
    )
    fact = Fact(
        id="fact_quote",
        text="TSLA quote snapshot: price 182.5 USD.",
        source_ids=[source.id],
        observed_at=source.fetched_at,
        metric="latest_price",
        symbol="TSLA",
    )
    claim = Claim(
        id="claim_research",
        text="Current sourced evidence supports research review, not a trading instruction.",
        evidence=[Evidence(fact_id=fact.id, source_id=source.id, quote=fact.text)],
        claim_type="supporting_factor",
    )
    run.sources.append(source)
    run.facts.append(fact)
    run.claims.append(claim)
    run.human_confirmation_points.append("请人工确认最新 quote 来源。")
    run.trace_path = "logs/research_traces/test.jsonl"

    output = render_investment_memo(run)
    rows = build_evidence_rows(run)
    payload = memo_trace_payload(run)

    assert "## Boundary Statement" in output
    assert "## Evidence Table" in output
    assert "claim_research" in output
    assert "fact_quote" in output
    assert "src_quote" in output
    assert "2026-06-04T00:00:00+00:00" in output
    assert rows[0].claim_id == "claim_research"
    assert payload["format"] == "investment_memo_v1"
    assert payload["evidence_row_count"] == 1
