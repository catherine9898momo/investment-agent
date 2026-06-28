from src.research.attribution_planner import build_attribution_plan
from src.research.models import IntentRoute, ResolvedEntity, TimeWindow


def test_drop_attribution_plan_requires_sector_and_peer_context() -> None:
    plan = build_attribution_plan(
        IntentRoute("news_explanation", "用户询问涨跌原因。"),
        ResolvedEntity("美光", "MU", "Micron"),
        TimeWindow("最近", "2026-06-01", "2026-06-07"),
        "美光最近为什么会大跌？",
    )

    keys = {need.key for need in plan.needs}
    assert plan.question_type == "price_drop"
    assert {"price_move", "news_events", "corporate_actions", "sector_move", "peer_moves"}.issubset(keys)
    assert {"NVDA", "AMD", "AVGO"}.issubset(set(plan.peer_symbols))
    assert {"WDC", "STX", "SNDK"}.issubset(set(plan.peer_symbols))


def test_attribution_plan_uses_configured_peer_resolver_for_mu() -> None:
    plan = build_attribution_plan(
        IntentRoute("news_explanation", "用户询问涨跌原因。"),
        ResolvedEntity("美光", "MU", "Micron"),
        TimeWindow("最近", "2026-06-01", "2026-06-07"),
        "美光最近为什么会大跌？",
    )

    assert {"NVDA", "AMD", "AVGO"}.issubset(set(plan.peer_symbols))
    assert {"WDC", "STX", "SNDK"}.issubset(set(plan.peer_symbols))
    assert {"QQQ", "SMH", "SOXX"}.issubset(set(plan.index_symbols))


def test_general_attribution_plan_uses_configured_peer_context_for_moutai() -> None:
    plan = build_attribution_plan(
        IntentRoute("unknown_research", "用户询问近期表现。"),
        ResolvedEntity("茅台", "600519.SS", "贵州茅台"),
        TimeWindow("最近", "2026-06-21", "2026-06-28"),
        "茅台最近表现怎么样？",
    )

    keys = {need.key for need in plan.needs}
    assert plan.question_type == "general"
    assert {"sector_move", "peer_moves"}.issubset(keys)
    assert {"000858.SZ", "000568.SZ"}.issubset(set(plan.peer_symbols))
    assert {"000300.SS", "510300.SS"}.issubset(set(plan.index_symbols))
