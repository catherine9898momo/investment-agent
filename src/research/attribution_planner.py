"""涨跌原因归因计划。"""

from __future__ import annotations

from src.research.models import AttributionNeed, AttributionPlan, IntentRoute, PeerUniverseItem, ResolvedEntity, TimeWindow
from src.research.peer_resolver import resolve_sector_peer_set


def build_attribution_plan(route: IntentRoute, entity: ResolvedEntity, time_window: TimeWindow, user_query: str) -> AttributionPlan:
    """/**
     * 为“为什么涨/跌”类问题生成必须核验的原因清单。
     *
     * @param route - 意图路由。
     * @param entity - 已解析标的。
     * @param time_window - 已解析时间窗口。
     * @param user_query - 用户原始问题。
     * @returns AttributionPlan。
     */
    """

    question_type = _question_type(user_query, route)
    needs = [
        AttributionNeed("price_move", f"核验 {entity.symbol} 在{time_window.label}的实际涨跌幅。"),
        AttributionNeed("news_events", "核验该时间窗口内与公司直接相关的新闻事件。"),
        AttributionNeed("corporate_actions", "排除拆股、股息等公司行动造成的价格变化。"),
    ]
    if question_type in {"price_drop", "price_rise"}:
        needs.extend([
            AttributionNeed("sector_move", "核验半导体/所在行业 ETF 或指数是否同步波动。"),
            AttributionNeed("peer_moves", "核验主要同行是否同步波动，区分个股因素和板块因素。"),
            AttributionNeed("macro_context", "核验 Nasdaq/利率/宏观风险偏好是否构成背景。", required=False),
            AttributionNeed("earnings_or_guidance", "核验财报、指引或重要产业链公司消息是否影响预期。", required=False),
            AttributionNeed("analyst_actions", "核验评级或目标价变化。", required=False),
        ])
    peer_set = resolve_sector_peer_set(entity) if question_type in {"price_drop", "price_rise"} else None
    return AttributionPlan(
        question_type=question_type,
        needs=needs,
        peer_symbols=[peer.symbol for peer in peer_set.peers] if peer_set else [],
        index_symbols=[index.symbol for index in peer_set.sector_indexes] if peer_set else [],
        peer_items=[PeerUniverseItem(peer.symbol, peer.group, peer.label) for peer in peer_set.peers] if peer_set else [],
        index_items=[PeerUniverseItem(index.symbol, index.group, index.label) for index in peer_set.sector_indexes] if peer_set else [],
    )


def _question_type(user_query: str, route: IntentRoute) -> str:
    if any(term in user_query for term in ("跌", "大跌", "下跌", "暴跌", "回调", "下挫")):
        return "price_drop"
    if any(term in user_query for term in ("涨", "大涨", "上涨", "反弹")):
        return "price_rise"
    if route.route == "news_explanation":
        return "general"
    return "general"
