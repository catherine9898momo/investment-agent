"""把普通 Fact 转成 verified/missing fact 表。"""

from __future__ import annotations

from src.research.models import AttributionPlan, Fact, MissingFact, VerifiedFact, new_id

_METRIC_TO_FACT_TYPE = {
    "latest_price": "price_move",
    "five_day_close_range": "price_move",
    "news_tone": "news_events",
    "unknown_news": "news_events",
    "corporate_actions": "corporate_actions",
    "investment_preferences": "user_preferences",
    "sector_move": "sector_move",
    "peer_moves": "peer_moves",
    "analyst_actions": "analyst_actions",
    "earnings_or_guidance": "earnings_or_guidance",
    "macro_context": "macro_context",
    "fundamentals": "fundamentals",
    "sec_company_facts": "sec_filings",
    "stock_search": "market_universe",
    "market_list": "market_universe",
}


def build_verified_fact_table(facts: list[Fact], attribution_plan: AttributionPlan | None) -> tuple[list[VerifiedFact], list[MissingFact]]:
    """/**
     * 生成 verified facts 和 missing facts。
     *
     * @param facts - normalizer 产出的原始事实。
     * @param attribution_plan - 当前问题的归因计划。
     * @returns (verified_facts, missing_facts)。
     *
     * @remarks P0 版本只做确定性映射：已有工具事实进入 verified/partial，
     * attribution plan 中没有被覆盖的需求进入 missing facts。
     */
    """

    verified: list[VerifiedFact] = []
    covered: set[str] = set()
    for fact in facts:
        fact_type = _fact_type_for(fact)
        if fact_type is None:
            continue
        status = "partial" if _is_limited_fact(fact) else "verified"
        confidence = "low" if status == "partial" else "medium"
        verified.append(
            VerifiedFact(
                id=new_id("vfact"),
                fact_type=fact_type,
                text=fact.text,
                source_ids=fact.source_ids,
                observed_at=fact.observed_at,
                confidence=confidence,
                verification_status=status,
                raw_fact_id=fact.id,
                value=fact.value,
            )
        )
        if status == "verified":
            covered.add(fact_type)

    missing: list[MissingFact] = []
    if attribution_plan:
        for need in attribution_plan.needs:
            if need.key not in covered:
                missing.append(MissingFact(need.key, need.description, need.required))
    return verified, missing


def _fact_type_for(fact: Fact) -> str | None:
    if fact.metric in _METRIC_TO_FACT_TYPE:
        return _METRIC_TO_FACT_TYPE[fact.metric or ""]
    if fact.metric and fact.metric.startswith(("failure_", "missing_", "stale_", "unknown_", "conflicting_", "data_quality_", "price_provenance_")):
        return fact.metric
    return None


def _is_limited_fact(fact: Fact) -> bool:
    return bool(fact.metric and fact.metric.startswith(("failure_", "missing_", "stale_", "unknown_", "conflicting_", "data_quality_", "price_provenance_")))
