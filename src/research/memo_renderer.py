"""Deterministic investment memo renderer for research runs."""

from __future__ import annotations

from dataclasses import dataclass

from src.research.models import Claim, Evidence, Fact, ResearchRunState, Source


MEMO_SECTIONS = [
    "Boundary Statement",
    "Executive Summary",
    "Evidence Table",
    "What We Know",
    "Risks",
    "Unknowns / Conflicts",
    "Freshness Notes",
    "User Preference Fit",
    "Human Confirmation Points",
    "Trace Reference",
]


@dataclass
class EvidenceRow:
    claim_id: str
    claim_type: str
    claim_text: str
    fact_id: str
    fact_metric: str
    fact_text: str
    source_id: str
    source_name: str
    source_fetched_at: str
    fact_observed_at: str


def render_investment_memo(run: ResearchRunState) -> str:
    """Render a guardrail-compatible memo from already-bound research objects."""
    supporting = [claim for claim in run.claims if claim.claim_type in {"fact_summary", "supporting_factor"}]
    risks = [claim for claim in run.claims if claim.claim_type == "risk_factor"]
    fit = [claim for claim in run.claims if claim.claim_type == "fit_assessment"]
    unknowns = [claim for claim in run.claims if claim.claim_type == "unknown"]
    rows = build_evidence_rows(run)

    sections = [
        "# Investment Research Memo",
        "",
        "## Boundary Statement",
        "这是一份基于可追踪证据的研究 memo，不是买入、卖出、加仓、减仓、清仓、持有或做空建议。",
        "",
        "## Executive Summary",
        *claim_lines(supporting[:2] + risks[:1] + unknowns[:1]),
        "",
        "## Evidence Table",
        *evidence_table_lines(rows),
        "",
        "## What We Know",
        *fact_lines(run.facts),
        *claim_lines(supporting),
        "",
        "## Risks",
        *claim_lines(risks),
        "- 风险: 行情、新闻、偏好和 corporate actions 都有数据源时效、覆盖范围和解释边界；正式决策前需要人工复核关键来源。",
        "",
        "## Unknowns / Conflicts",
        *claim_lines(unknowns),
        "- 未知项: 最新财报、交付量、毛利率、自由现金流、估值区间、管理层说明和多源新闻冲突尚未核验。",
        "",
        "## Freshness Notes",
        *freshness_lines(run),
        "",
        "## User Preference Fit",
        *claim_lines(fit),
        "",
        "## Human Confirmation Points",
        *[f"- {point}" for point in run.human_confirmation_points],
        "",
        "## Trace Reference",
        f"- Trace: {run.trace_path}",
    ]
    return "\n".join(sections)


def build_evidence_rows(run: ResearchRunState) -> list[EvidenceRow]:
    rows: list[EvidenceRow] = []
    for claim in run.claims:
        for evidence in claim.evidence:
            fact = run.fact_by_id(evidence.fact_id)
            source = run.source_by_id(evidence.source_id)
            if fact is None or source is None:
                continue
            rows.append(_evidence_row(claim, evidence, fact, source))
    return rows


def memo_trace_payload(run: ResearchRunState) -> dict[str, object]:
    rows = build_evidence_rows(run)
    return {
        "format": "investment_memo_v1",
        "sections": MEMO_SECTIONS,
        "evidence_row_count": len(rows),
        "claim_ids": [claim.id for claim in run.claims],
        "fact_ids": [fact.id for fact in run.facts],
        "source_ids": [source.id for source in run.sources],
    }


def claim_lines(claims: list[Claim]) -> list[str]:
    if not claims:
        return ["- 未生成对应 claim；需要更多可追踪事实或人工补充。"]
    lines = []
    for claim in claims:
        evidence_refs = [f"{e.fact_id}/{e.source_id}" for e in claim.evidence]
        lines.append(f"- {claim.text} 证据: {', '.join(evidence_refs)}")
    return lines


def fact_lines(facts: list[Fact]) -> list[str]:
    if not facts:
        return ["- 暂无可用 fact。"]
    return [
        (
            f"- {fact.text} 来源: {', '.join(fact.source_ids)}; "
            f"observed_at: {fact.observed_at}; metric: {fact.metric}"
        )
        for fact in facts
    ]


def evidence_table_lines(rows: list[EvidenceRow]) -> list[str]:
    if not rows:
        return ["- No evidence rows available; guardrail should block key claims without evidence."]
    lines = [
        "| Claim | Claim Type | Fact | Fact Metric | Source | Source fetched_at | Fact observed_at |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{_cell(row.claim_text)} ({row.claim_id}) | "
            f"{_cell(row.claim_type)} | "
            f"{_cell(row.fact_text)} ({row.fact_id}) | "
            f"{_cell(row.fact_metric)} | "
            f"{_cell(row.source_name)} ({row.source_id}) | "
            f"{_cell(row.source_fetched_at)} | "
            f"{_cell(row.fact_observed_at)} |"
        )
    return lines


def freshness_lines(run: ResearchRunState) -> list[str]:
    if not run.sources:
        return ["- No sources available; freshness cannot be assessed."]
    lines = [
        (
            f"- Source {source.id}: {source.name}; tool={source.tool_name}; "
            f"fetched_at={source.fetched_at}; reliability={source.reliability}"
        )
        for source in run.sources
    ]
    quality_facts = [fact for fact in run.facts if _is_data_quality_metric(fact.metric)]
    if quality_facts:
        lines.append("- Data quality limitations:")
        lines.extend(f"  - {fact.metric}: {fact.text}" for fact in quality_facts)
    return lines


def _evidence_row(claim: Claim, evidence: Evidence, fact: Fact, source: Source) -> EvidenceRow:
    return EvidenceRow(
        claim_id=claim.id,
        claim_type=claim.claim_type,
        claim_text=claim.text,
        fact_id=fact.id,
        fact_metric=fact.metric or "unknown_metric",
        fact_text=evidence.quote or fact.text,
        source_id=source.id,
        source_name=source.name,
        source_fetched_at=source.fetched_at,
        fact_observed_at=fact.observed_at,
    )


def _is_data_quality_metric(metric: str | None) -> bool:
    if not metric:
        return False
    return metric.startswith(("stale_", "missing_", "failure_", "unknown_", "conflicting_"))


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
