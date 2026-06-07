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
    assert plan.peer_symbols == ["NVDA", "AMD", "AVGO"]
