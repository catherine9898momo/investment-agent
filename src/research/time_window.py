"""用户问题的时间窗口解析。"""

from __future__ import annotations

from datetime import date, timedelta

from src.research.models import TimeWindow


def resolve_time_window(user_query: str, today: date | None = None) -> TimeWindow:
    """/**
     * 从用户问题中解析研究时间窗口。
     *
     * @param user_query - 用户原始问题。
     * @param today - 测试可注入的当前日期；默认使用系统日期。
     * @returns TimeWindow。
     *
     * @remarks 这是 P0 规则版本：先覆盖今天/昨天/本周/最近等高频表达，
     * 后续再接交易日历和财报事件窗口。
     */
    """

    current = today or date.today()
    query = user_query.lower()
    if "今天" in user_query or "today" in query:
        return TimeWindow("今天", current.isoformat(), current.isoformat(), "high", "用户明确提到今天。")
    if "昨天" in user_query or "yesterday" in query:
        day = current - timedelta(days=1)
        return TimeWindow("昨天", day.isoformat(), day.isoformat(), "high", "用户明确提到昨天。")
    if "本周" in user_query or "this week" in query:
        start = current - timedelta(days=current.weekday())
        return TimeWindow("本周", start.isoformat(), current.isoformat(), "high", "用户明确提到本周。")
    if any(term in user_query for term in ("最近", "大跌", "下跌", "暴跌", "回调", "为什么跌", "为什么会跌")):
        start = current - timedelta(days=7)
        return TimeWindow("最近 5 个交易日左右", start.isoformat(), current.isoformat(), "medium", "用户使用最近/涨跌归因表达，默认取约一周窗口。")
    start = current - timedelta(days=7)
    return TimeWindow("默认最近一周", start.isoformat(), current.isoformat(), "low", "用户未明确时间，使用保守默认窗口。")
