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
    assert "## 研究结论" in output
    assert "## 原因排序" in output
    assert "## 发生了什么" in output
    assert "## 关键依据" in output
    assert "## 风险与不确定性" in output
    assert "## 还需要确认" in output
    assert "## 数据来源与时效" in output
    assert "Trace 日志：logs/research_traces/test.jsonl" in output
    assert "交易建议" in output
    assert "claim_research" not in output
    assert "fact_quote" not in output
    assert "src_quote" not in output
    assert "## 证据表" not in output
    assert "## 研究计划" not in output
    assert rows[0].claim_id == "claim_research"
    assert payload["format"] == "investment_memo_v2"
    assert payload["evidence_row_count"] == 1



def test_render_investment_memo_filters_nan_history_close() -> None:
    run = ResearchRunState.start("帮我看 MU 最近为什么大跌？")
    source = Source(
        id="src_history",
        kind="tool_result",
        name="live price history",
        fetched_at="2026-06-10T00:00:00+00:00",
        tool_name="finance.get_history",
    )
    fact = Fact(
        id="fact_history",
        text="MU 5d close range: 864.01 to 1079.57; latest close nan.",
        source_ids=[source.id],
        observed_at=source.fetched_at,
        metric="five_day_close_range",
        value={
            "symbol": "MU",
            "period": "5d",
            "bars": [
                {"date": "2026-06-03", "close": 864.01},
                {"date": "2026-06-04", "close": 1079.57},
                {"date": "2026-06-10", "close": float("nan")},
            ],
        },
        symbol="MU",
    )
    run.sources.append(source)
    run.facts.append(fact)

    output = render_investment_memo(run)

    assert "nan" not in output.lower()
    assert "近 2 个有效交易日收盘价区间约为 864.01 到 1079.57，最新收盘价为 1079.57" in output



def test_render_investment_memo_explains_insufficient_history_without_range_claim() -> None:
    run = ResearchRunState.start("帮我看 MU 最近为什么大跌？")
    source = Source(
        id="src_quality",
        kind="tool_result",
        name="data quality checks",
        fetched_at="2026-06-10T00:00:00+00:00",
        tool_name="research.data_quality_check",
    )
    fact = Fact(
        id="fact_history_insufficient",
        text="Data quality limitation for MU: only 1 valid history close was available; cannot compute a close range or trend.",
        source_ids=[source.id],
        observed_at=source.fetched_at,
        metric="data_quality_history_insufficient",
        value={"valid_close_count": 1, "required_for_range": 2, "required_for_trend": 3},
        symbol="MU",
    )
    run.sources.append(source)
    run.facts.append(fact)

    output = render_investment_memo(run)

    assert "历史行情数据不足" in output
    assert "收盘价区间约为" not in output


def test_render_investment_memo_uses_chinese_attribution_labels_and_avoids_dominant_language() -> None:
    from src.research.models import AttributionCause

    run = ResearchRunState.start("帮我看 MU 最近为什么大跌？")
    run.attribution_causes = [
        AttributionCause(
            label="半导体与存储链条同步回调",
            level="likely_factor",
            support_fact_ids=["fact_sector", "fact_peer"],
            missing_fact_types=[],
            confidence="medium",
            rationale="sector and peer coverage is partial but sufficient for a likely factor.",
            next_checks=["继续核验 SOXX 和 STX 数据"],
        )
    ]

    output = render_investment_memo(run)

    assert "归因证据矩阵" in output
    assert "较可能因素" in output
    assert "likely_factor" not in output
    assert "主导" not in output
