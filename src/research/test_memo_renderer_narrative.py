from src.research.memo_renderer import render_investment_memo
from src.research.models import AttributionCause, Fact, ResearchRunState, Source, VerifiedFact


def test_memo_renders_user_facing_narrative_sections_without_debug_ids() -> None:
    run = ResearchRunState.start("美光 MU 最近为什么大跌？")
    source = Source(
        id="src_news",
        kind="tool_result",
        name="live news",
        fetched_at="2026-06-28T00:00:00+00:00",
        tool_name="news.get_news",
    )
    run.sources = [source]
    run.facts = [
        Fact(
            id="fact_news",
            text="Recent news snapshot.",
            source_ids=[source.id],
            observed_at=source.fetched_at,
            metric="news_tone",
            value={"items": [{"title": "Micron Stock Falls After Memory Rivals SK Hynix and Samsung Sink"}]},
            symbol="MU",
        ),
        Fact(
            id="fact_quote",
            text="MU quote snapshot.",
            source_ids=[source.id],
            observed_at=source.fetched_at,
            metric="latest_price",
            value={"symbol": "MU", "price": 94.0, "currency": "USD", "change_pct": -6.0},
            symbol="MU",
        ),
    ]
    run.verified_facts = [
        VerifiedFact("vf_price", "price_move", "MU 下跌 6%。", ["src_news"], "2026-06-28", raw_fact_id="fact_quote"),
        VerifiedFact("vf_peer", "peer_moves", "同行同步下跌。", ["src_news"], "2026-06-28", raw_fact_id="fact_news"),
    ]
    run.attribution_causes = [
        AttributionCause(
            label="板块/同行同步波动",
            level="likely_factor",
            support_fact_ids=["vf_price", "vf_peer"],
            confidence="medium",
        )
    ]

    output = render_investment_memo(run)

    assert "## 一句话结论" in output
    assert "## 最可能的原因" in output
    assert "## 基本面是否变坏" in output
    assert output.index("板块/同行同步波动") < output.index("## 归因证据矩阵")
    assert "fact_" not in output
    assert "source_" not in output
    assert "这不是交易建议" in output



def test_memo_interprets_quantitative_market_context_instead_of_listing_raw_facts() -> None:
    run = ResearchRunState.start("美光 MU 最近为什么大跌？")
    source = Source(
        id="src_market",
        kind="tool_result",
        name="live market data",
        fetched_at="2026-06-28T00:00:00+00:00",
        tool_name="finance.get_history",
    )
    run.sources = [source]
    run.facts = [
        Fact(
            id="fact_quote",
            text="MU quote snapshot.",
            source_ids=[source.id],
            observed_at=source.fetched_at,
            metric="latest_price",
            value={"symbol": "MU", "price": 94.0, "currency": "USD", "change_pct": -6.0},
            symbol="MU",
        ),
        Fact(
            id="fact_history",
            text="MU 5d close range.",
            source_ids=[source.id],
            observed_at=source.fetched_at,
            metric="five_day_close_range",
            value={"bars": [{"close": 100.0}, {"close": 110.0}, {"close": 90.0}, {"close": 94.0}]},
            symbol="MU",
        ),
    ]
    run.verified_facts = [
        VerifiedFact("vf_price", "price_move", "MU 下跌 6%。", [source.id], source.fetched_at, value={"change_pct": -6.0}),
        VerifiedFact(
            "vf_sector",
            "sector_move",
            "板块同步下跌。",
            [source.id],
            source.fetched_at,
            value={"items": [{"symbol": "SMH", "change_pct": -3.0}, {"symbol": "QQQ", "change_pct": -2.0}], "success_count": 2},
        ),
        VerifiedFact(
            "vf_peer",
            "peer_moves",
            "同行同步下跌。",
            [source.id],
            source.fetched_at,
            value={"items": [{"symbol": "WDC", "change_pct": -4.2}, {"symbol": "STX", "change_pct": -3.8}, {"symbol": "NVDA", "change_pct": -1.3}], "success_count": 3},
        ),
    ]
    run.attribution_causes = [
        AttributionCause(
            label="板块/同行同步波动",
            level="likely_factor",
            support_fact_ids=["vf_price", "vf_sector", "vf_peer"],
            confidence="medium",
        )
    ]

    output = render_investment_memo(run)

    assert "MU 自身约下跌 6.00%" in output
    assert "板块/指数平均约下跌 2.50%" in output
    assert "同行平均约下跌 3.10%" in output
    assert "位于近 5 日收盘区间的 20% 分位附近" in output
    reason_section = output.split("## 最可能的原因", 1)[1].split("## 基本面是否变坏", 1)[0]
    assert "MU、板块/指数和同行都在同一窗口下跌" in reason_section
    assert "MU 跌幅重于对照均值" in reason_section
    assert "- 价格：" not in output
    assert "- 新闻：当前召回" not in output


def test_memo_keeps_explicit_confirmation_word_after_narrative_section_rename() -> None:
    run = ResearchRunState.start("研究 MU")
    run.human_confirmation_points = ["你关注的是短期交易解释还是中长期 thesis？"]

    output = render_investment_memo(run)

    assert "请确认" in output
