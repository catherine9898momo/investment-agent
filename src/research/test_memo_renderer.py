from src.research.memo_renderer import build_evidence_rows, memo_trace_payload, render_investment_memo
from src.research.models import Claim, Evidence, Fact, ResearchRunState, Source


def test_render_investment_memo_is_user_readable_and_keeps_debug_ids_out_of_body() -> None:
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
        value={"symbol": "TSLA", "price": 182.5, "currency": "USD", "change_pct": 1.78},
        symbol="TSLA",
    )
    claim = Claim(
        id="claim_research",
        text="当前证据支持继续研究 TSLA，但不能生成交易指令。",
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

    assert "# TSLA 研究简报" in output
    assert "## 先说结论" in output
    assert "## 发生了什么" in output
    assert "## 关键依据" in output
    assert "## 风险与不确定性" in output
    assert "## 还需要确认" in output
    assert "## 数据来源与时效" in output
    assert "交易建议" in output
    assert "claim_research" not in output
    assert "fact_quote" not in output
    assert "src_quote" not in output
    assert "## 证据表" not in output
    assert "## 研究计划" not in output
    assert rows[0].claim_id == "claim_research"
    assert payload["format"] == "investment_memo_v2"
    assert payload["evidence_row_count"] == 1
