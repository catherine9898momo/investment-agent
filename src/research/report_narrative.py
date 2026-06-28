"""Build user-facing narrative models from traceable research run state."""

from __future__ import annotations

from dataclasses import dataclass

from src.research.models import ResearchRunState, VerifiedFact
from src.research.news_event_classifier import NewsEvent, classify_news_events


@dataclass(frozen=True)
class NarrativeCause:
    label: str
    explanation: str
    attribution_level: str
    confidence: str
    supporting_event_types: list[str]
    supporting_fact_types: list[str]


@dataclass(frozen=True)
class ReportNarrative:
    title: str
    one_line_conclusion: str
    key_move: str | None
    primary_cause: NarrativeCause
    secondary_causes: list[NarrativeCause]
    fundamental_readthrough: str | None
    evidence_events: list[NewsEvent]
    remaining_gaps: list[str]
    quality_note: str


def build_report_narrative(run: ResearchRunState) -> ReportNarrative:
    symbol = run.resolved_entity.symbol if run.resolved_entity else next((fact.symbol for fact in run.facts if fact.symbol), "标的")
    company = run.resolved_entity.company_query if run.resolved_entity else None
    title = f"{company}（{symbol}）研究简报" if company and company != symbol else f"{symbol} 研究简报"
    events = classify_news_events(run.facts)
    key_move = _key_move(run)
    primary_cause = _primary_cause(run, events, premise_invalid=_drop_premise_invalid(run))
    remaining_gaps = _remaining_gaps(run)
    one_line = _one_line_conclusion(primary_cause, key_move)
    return ReportNarrative(
        title=title,
        one_line_conclusion=one_line,
        key_move=key_move,
        primary_cause=primary_cause,
        secondary_causes=_secondary_causes(events, primary_cause),
        fundamental_readthrough=_fundamental_readthrough(events),
        evidence_events=events,
        remaining_gaps=remaining_gaps,
        quality_note="已按当前可核验证据生成，缺口会在不确定性中单独列出。",
    )


def _primary_cause(run: ResearchRunState, events: list[NewsEvent], premise_invalid: bool = False) -> NarrativeCause:
    if premise_invalid:
        return NarrativeCause(
            label="暂不做下跌归因",
            explanation="当前可核验价格快照没有确认下跌，先需要确认具体日期、交易时段或价格口径。",
            attribution_level="unsupported",
            confidence="low",
            supporting_event_types=[],
            supporting_fact_types=["price_move"],
        )
    if run.attribution_causes:
        cause = run.attribution_causes[0]
        return NarrativeCause(
            label=cause.label,
            explanation=_cause_explanation(cause.label, cause.level, cause.rationale),
            attribution_level=cause.level,
            confidence=cause.confidence,
            supporting_event_types=[event.event_type for event in events if event.is_primary],
            supporting_fact_types=_supporting_fact_types(run.verified_facts, cause.support_fact_ids),
        )
    return NarrativeCause(
        label="当前证据不足以形成归因",
        explanation="价格、新闻、板块或同行证据还不足，不能把某个因素写成主要原因。",
        attribution_level="unsupported",
        confidence="low",
        supporting_event_types=[event.event_type for event in events if event.is_primary],
        supporting_fact_types=[],
    )


def _supporting_fact_types(verified_facts: list[VerifiedFact], support_ids: list[str]) -> list[str]:
    support_id_set = set(support_ids)
    fact_types: list[str] = []
    for fact in verified_facts:
        if fact.id in support_id_set or (fact.raw_fact_id and fact.raw_fact_id in support_id_set):
            fact_types.append(fact.fact_type)
    return fact_types


def _key_move(run: ResearchRunState) -> str | None:
    quote = next((fact for fact in run.facts if fact.metric == "latest_price"), None)
    value = quote.value if quote else None
    if not isinstance(value, dict) or not isinstance(value.get("change_pct"), (int, float)):
        return None
    change = float(value["change_pct"])
    direction = "上涨" if change > 0 else "下跌" if change < 0 else "持平"
    price = value.get("price")
    currency = value.get("currency") or ""
    return f"最新价格快照为 {price} {currency}，相对前收盘约{direction} {abs(change):.2f}%。"


def _drop_premise_invalid(run: ResearchRunState) -> bool:
    if not any(term in run.user_query for term in ("跌", "大跌", "下跌", "暴跌", "回调", "下挫")):
        return False
    quote = next((fact for fact in run.facts if fact.metric == "latest_price"), None)
    value = quote.value if quote else None
    return isinstance(value, dict) and isinstance(value.get("change_pct"), (int, float)) and float(value["change_pct"]) >= 0


def _remaining_gaps(run: ResearchRunState) -> list[str]:
    gaps: list[str] = []
    for missing in run.missing_facts:
        gaps.append(missing.reason)
    for cause in run.attribution_causes:
        for fact_type in cause.missing_fact_types:
            text = f"仍需补齐 {fact_type}。"
            if text not in gaps:
                gaps.append(text)
    return gaps


def _one_line_conclusion(cause: NarrativeCause, key_move: str | None) -> str:
    level = _level_label(cause.attribution_level)
    move = f"{key_move} " if key_move else ""
    if cause.label == "暂不做下跌归因":
        return f"{move}当前可核验价格不支持“最近大跌”这个前提，应先确认具体日期、交易时段或价格口径。"
    if cause.attribution_level == "unsupported":
        return f"{move}当前证据不足以形成明确归因。"
    return f"{move}当前最重要的解释是“{cause.label}”，归因等级为“{level}”。"


def _secondary_causes(events: list[NewsEvent], primary_cause: NarrativeCause) -> list[NarrativeCause]:
    causes: list[NarrativeCause] = []
    seen_event_types: set[str] = set(primary_cause.supporting_event_types)
    for event in events:
        if event.is_primary or event.event_type in seen_event_types:
            continue
        seen_event_types.add(event.event_type)
        causes.append(
            NarrativeCause(
                label=event.label,
                explanation=event.summary,
                attribution_level="background_context",
                confidence=event.confidence,
                supporting_event_types=[event.event_type],
                supporting_fact_types=["news_events"],
            )
        )
    return causes[:3]


def _fundamental_readthrough(events: list[NewsEvent]) -> str | None:
    if any(event.event_type == "earnings_or_guidance" for event in events):
        return "已有新闻线索涉及财报、指引或利润率预期；股价下跌不必然等于基本面恶化，也可能是高预期后的重新定价。"
    if any(event.event_type == "sector_peer" for event in events):
        return "当前更像需要先区分公司自身基本面变化和板块/同行同步波动；仅凭股价下跌不能判断基本面已经变坏。"
    return None


def _cause_explanation(label: str, level: str, rationale: str) -> str:
    if "板块" in label or "同行" in label:
        return "板块和同行同窗口波动为本轮解释提供了更强支撑，但仍要结合新闻与基本面确认。"
    if level == "candidate_factor":
        return "已有价格或新闻线索，但证据覆盖还不足，只能作为候选解释。"
    return rationale or "该因素来自已核验事实和归因评估。"


def _level_label(level: str) -> str:
    return {
        "confirmed_cause": "已确认原因",
        "likely_factor": "较可能因素",
        "candidate_factor": "候选因素",
        "background_context": "背景信息",
        "unsupported": "证据不支持",
    }.get(level, level)

