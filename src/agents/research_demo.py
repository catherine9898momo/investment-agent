"""Evidence-backed research demo for the P0 investment research boundary.

Default mode uses deterministic fixture data so the guardrail and trace path can
be validated without network access. Use --data-source live to reuse the real
MCP server backend functions for quote/history/news/corporate-actions results.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict

from src.research.evaluator import evaluate_research_output
from src.research.models import Claim, ResearchRunState, to_json
from src.research.normalizers import normalize_tool_result_bundle
from src.research.synthesizer import bind_claims_to_evidence, make_synthesizer
from src.research.tool_provider import ToolResultBundle, make_tool_provider
from src.research.trace import TraceLogger


DEFAULT_QUERY = "帮我看 TSLA 最近是否还值得继续关注。"
DEFAULT_SYMBOL = "TSLA"
DEFAULT_COMPANY_QUERY = "Tesla"


def build_research_run(
    user_query: str,
    synthesizer_name: str = "mock",
    data_source: str = "fixture",
    symbol: str = DEFAULT_SYMBOL,
    company_query: str = DEFAULT_COMPANY_QUERY,
    history_days: int = 5,
    news_days: int = 7,
) -> ResearchRunState:
    provider = make_tool_provider(data_source)
    bundle = provider.fetch(symbol, company_query, history_days, news_days)
    return build_research_run_from_bundle(
        user_query,
        bundle,
        synthesizer_name=synthesizer_name,
        symbol=symbol,
    )


def build_research_run_from_bundle(
    user_query: str,
    bundle: ToolResultBundle,
    synthesizer_name: str = "mock",
    symbol: str = DEFAULT_SYMBOL,
) -> ResearchRunState:
    run = ResearchRunState.start(user_query=user_query)
    trace = TraceLogger(run)
    trace.append("run_started", {"run_id": run.run_id, "query": user_query})

    trace_tool_results(trace, bundle)

    normalized = normalize_tool_result_bundle(bundle, symbol)
    run.sources.extend(normalized.sources)
    run.facts.extend(normalized.facts)

    for source in run.sources:
        trace.append("source_added", source)
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

def trace_tool_results(trace: TraceLogger, bundle: ToolResultBundle) -> None:
    trace.append("tool_result", {"tool": "memory.get_preferences", "result": bundle.preferences})
    trace.append("tool_result", {"tool": "finance.get_quote", "result": bundle.quote})
    trace.append("tool_result", {"tool": "finance.get_history", "result": bundle.history})
    trace.append("tool_result", {"tool": "news.get_news", "result": bundle.news})
    trace.append("tool_result", {"tool": "corporate_actions.get_corporate_actions", "result": bundle.corporate_actions})


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
        "# Investment Research Snapshot",
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
        "- 风险: 行情、新闻和 corporate actions 都有数据源时效和覆盖边界；正式决策前需要人工复核关键来源。",
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
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--company-query", default=DEFAULT_COMPANY_QUERY)
    parser.add_argument("--history-days", type=int, default=5)
    parser.add_argument("--news-days", type=int, default=7)
    parser.add_argument(
        "--data-source",
        choices=["fixture", "live"],
        default="fixture",
        help="fixture is deterministic; live reuses the real MCP server backend functions.",
    )
    parser.add_argument(
        "--synthesizer",
        choices=["mock", "anthropic"],
        default="mock",
        help="mock is deterministic and offline; anthropic requires ANTHROPIC_API_KEY and network access.",
    )
    parser.add_argument("--json", action="store_true", help="Print run state JSON instead of markdown output.")
    args = parser.parse_args()

    run = build_research_run(
        args.query,
        synthesizer_name=args.synthesizer,
        data_source=args.data_source,
        symbol=args.symbol,
        company_query=args.company_query,
        history_days=args.history_days,
        news_days=args.news_days,
    )
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
