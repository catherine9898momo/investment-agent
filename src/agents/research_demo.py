"""Evidence-backed research demo for the P0 investment research boundary.

Default mode uses deterministic local fixture data so the guardrail and trace
path can be validated without network access. Use --live later to swap fixture
tool outputs for the existing MCP backend helpers.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from typing import Any

from src.memory import store
from src.research.evaluator import evaluate_research_output
from src.research.models import Claim, Fact, ResearchRunState, Source, new_id, to_json, utc_now_iso
from src.research.synthesizer import bind_claims_to_evidence, make_synthesizer
from src.research.trace import TraceLogger


DEFAULT_QUERY = "帮我看 TSLA 最近是否还值得继续关注。"


def _source(kind: str, name: str, tool_name: str, reliability: str = "medium") -> Source:
    return Source(
        id=new_id("src"),
        kind=kind,  # type: ignore[arg-type]
        name=name,
        tool_name=tool_name,
        fetched_at=utc_now_iso(),
        reliability=reliability,  # type: ignore[arg-type]
    )


def _add_fact(
    run: ResearchRunState,
    text: str,
    source: Source,
    metric: str | None = None,
    value: Any | None = None,
    symbol: str = "TSLA",
) -> Fact:
    fact = Fact(
        id=new_id("fact"),
        text=text,
        source_ids=[source.id],
        observed_at=source.fetched_at,
        metric=metric,
        value=value,
        symbol=symbol,
    )
    run.facts.append(fact)
    return fact


def _fixture_tool_results() -> dict[str, Any]:
    """Local stand-in for MCP tool results.

    Values are intentionally marked as demo fixture snapshots. They validate
    traceability and guardrails, not real-time TSLA research.
    """
    return {
        "quote": {
            "symbol": "TSLA",
            "price": 182.50,
            "previous_close": 179.30,
            "change_pct": 1.78,
            "currency": "USD",
        },
        "history": {
            "symbol": "TSLA",
            "period": "5d",
            "bars": [
                {"date": "2026-05-26", "close": 176.20},
                {"date": "2026-05-27", "close": 178.90},
                {"date": "2026-05-28", "close": 181.10},
                {"date": "2026-05-29", "close": 179.30},
                {"date": "2026-06-01", "close": 182.50},
            ],
        },
        "news": {
            "query": "Tesla",
            "days": 7,
            "items": [
                {
                    "title": "Demo fixture: Tesla delivery and margin discussion remains mixed",
                    "source": "Local Demo News",
                    "published": "2026-06-01T12:00:00+00:00",
                    "link": "local-fixture://news/tesla-mixed-margin",
                },
                {
                    "title": "Demo fixture: EV demand and competition remain key watch points",
                    "source": "Local Demo News",
                    "published": "2026-05-31T12:00:00+00:00",
                    "link": "local-fixture://news/ev-demand-competition",
                },
            ],
        },
    }


def build_research_run(user_query: str, synthesizer_name: str = "mock") -> ResearchRunState:
    run = ResearchRunState.start(user_query=user_query)
    trace = TraceLogger(run)
    trace.append("run_started", {"run_id": run.run_id, "query": user_query})

    preferences = store.get_all_preferences()
    if not preferences:
        preferences = {
            "style": "价值投资研究优先，避免短线交易建议",
            "risk": "偏好先确认风险和反证，再讨论是否继续研究",
        }

    fixture = _fixture_tool_results()
    trace.append("tool_result", {"tool": "memory.get_preferences", "result": preferences})
    trace.append("tool_result", {"tool": "finance.get_quote", "result": fixture["quote"]})
    trace.append("tool_result", {"tool": "finance.get_history", "result": fixture["history"]})
    trace.append("tool_result", {"tool": "news.get_news", "result": fixture["news"]})

    pref_source = _source("user_memory", "User investment preferences", "memory.get_preferences", "high")
    quote_source = _source("local_fixture", "Demo quote snapshot", "finance.get_quote", "medium")
    history_source = _source("local_fixture", "Demo 5-day price history", "finance.get_history", "medium")
    news_source = _source("local_fixture", "Demo Google News snapshot", "news.get_news", "medium")
    run.sources.extend([pref_source, quote_source, history_source, news_source])
    for source in run.sources:
        trace.append("source_added", source)

    quote = fixture["quote"]
    history = fixture["history"]
    news = fixture["news"]

    _add_fact(
        run,
        f"TSLA demo quote snapshot: price {quote['price']} {quote['currency']}, change {quote['change_pct']}% vs previous close.",
        quote_source,
        metric="latest_price",
        value=quote["price"],
    )
    _add_fact(
        run,
        f"TSLA demo 5-day closes range from {history['bars'][0]['close']} to {history['bars'][-1]['close']} USD.",
        history_source,
        metric="five_day_close_range",
        value=[bar["close"] for bar in history["bars"]],
    )
    _add_fact(
        run,
        "Recent demo news fixture is mixed: delivery/margin discussion plus EV demand and competition watch points.",
        news_source,
        metric="news_tone",
        value=[item["title"] for item in news["items"]],
    )
    _add_fact(
        run,
        f"User preference snapshot: {preferences}",
        pref_source,
        metric="investment_preferences",
        value=preferences,
    )

    for fact in run.facts:
        trace.append("fact_added", fact)

    synthesizer = make_synthesizer(synthesizer_name)
    synthesis = synthesizer.synthesize(run)
    trace.append("synthesis_result", synthesis)

    run.claims.extend(bind_claims_to_evidence(run, synthesis))
    run.human_confirmation_points = synthesis.human_confirmation_points
    run.raw_synthesis = synthesis.raw_model_output
    for claim in run.claims:
        trace.append("claim_added", claim)

    output = render_research_output(run)
    guardrail = evaluate_research_output(run, output)
    run.guardrail = guardrail
    run.final_output = output
    run.status = "completed" if guardrail.passed else "blocked"

    trace.append("final_output", {"text": output})
    trace.append("guardrail_result", guardrail)
    trace.append("run_completed", asdict(run))
    return run


def render_research_output(run: ResearchRunState) -> str:
    source_lines = [
        f"- {source.id}: {source.name}; tool={source.tool_name}; fetched_at={source.fetched_at}; reliability={source.reliability}"
        for source in run.sources
    ]
    fact_lines = [
        f"- {fact.text} 来源: {', '.join(fact.source_ids)}; 时间: {fact.observed_at}"
        for fact in run.facts
    ]
    supporting = [claim for claim in run.claims if claim.claim_type == "supporting_factor"]
    risks = [claim for claim in run.claims if claim.claim_type == "risk_factor"]
    fit = [claim for claim in run.claims if claim.claim_type == "fit_assessment"]
    unknowns = [claim for claim in run.claims if claim.claim_type == "unknown"]

    def claim_lines(claims: list[Claim]) -> list[str]:
        lines = []
        for claim in claims:
            evidence_refs = [f"{e.fact_id}/{e.source_id}" for e in claim.evidence]
            lines.append(f"- {claim.text} 证据: {', '.join(evidence_refs)}")
        return lines

    sections = [
        "# TSLA Research Snapshot (demo fixture)",
        "",
        "边界声明: 这是一份研究摘要，不是买入、卖出、加仓、减仓或清仓建议。",
        "",
        "## Key Facts",
        *fact_lines,
        "",
        "## Sources",
        *source_lines,
        "",
        "## Supporting Factors",
        *claim_lines(supporting),
        "",
        "## Risk Factors",
        *claim_lines(risks),
        "- 风险: 本演示默认使用 local fixture，不代表实时市场数据；正式运行必须替换为 live tool result。",
        "",
        "## Unknowns / Conflicts",
        *claim_lines(unknowns),
        "- 未知项: 最新财报、交付量、毛利率、自由现金流、估值区间、管理层说明和多源新闻冲突尚未核验。",
        "",
        "## Match With User Principles",
        *claim_lines(fit),
        "",
        "## Human Confirmation Points",
        *[f"- {point}" for point in run.human_confirmation_points],
        "",
        f"Trace: {run.trace_path}",
    ]
    return "\n".join(sections)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument(
        "--synthesizer",
        choices=["mock", "anthropic"],
        default="mock",
        help="mock is deterministic and offline; anthropic requires ANTHROPIC_API_KEY and network access.",
    )
    parser.add_argument("--json", action="store_true", help="Print run state JSON instead of markdown output.")
    args = parser.parse_args()

    run = build_research_run(args.query, synthesizer_name=args.synthesizer)
    if args.json:
        print(to_json(run))
    else:
        print(run.final_output)
        print()
        print("Guardrail:", "PASS" if run.guardrail and run.guardrail.passed else "BLOCKED")
        if run.guardrail:
            for check in run.guardrail.checks:
                status = "PASS" if check.passed else "FAIL"
                print(f"- {status} {check.name}: {check.message}")


if __name__ == "__main__":
    main()
