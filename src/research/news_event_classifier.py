"""Deterministic news event classification for report narrative rendering."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from src.research.models import Fact


NewsEventType = Literal[
    "earnings_or_guidance",
    "sector_peer",
    "ai_trade",
    "macro_risk",
    "analyst_action",
    "company_specific",
    "corporate_action",
    "valuation_or_positioning",
    "unknown",
]


@dataclass(frozen=True)
class NewsEvent:
    event_type: NewsEventType
    label: str
    summary: str
    supporting_fact_ids: list[str]
    source_titles: list[str]
    confidence: Literal["high", "medium", "low"] = "medium"
    is_primary: bool = False


_EVENT_RULES: list[tuple[NewsEventType, tuple[str, ...], str, str]] = [
    (
        "earnings_or_guidance",
        ("earnings", "revenue", "eps", "guidance", "outlook", "forecast", "results", "profit", "margin", "财报", "指引", "营收", "利润率", "业绩"),
        "财报/指引重新定价",
        "新闻线索指向财报、指引或利润率预期，股价反应可能来自市场对未来业绩路径的重新定价。",
    ),
    (
        "analyst_action",
        ("upgrade", "downgrade", "price target", "rating", "analyst", "上调", "下调", "目标价", "评级", "分析师"),
        "分析师观点变化",
        "新闻线索指向评级或目标价变化，这通常会影响短期预期和资金情绪。",
    ),
    (
        "ai_trade",
        ("ai", "nvidia", "data center", "hbm", "accelerator", "人工智能", "英伟达", "数据中心"),
        "AI 交易预期波动",
        "新闻线索指向 AI、数据中心或 HBM 需求，股价可能受高预期兑现和风险偏好变化影响。",
    ),
    (
        "sector_peer",
        ("peers", "rivals", "sk hynix", "samsung", "semiconductor", "chip", "memory", "kospi", "同行", "竞争对手", "半导体", "芯片", "存储", "板块"),
        "板块/同行同步信号",
        "新闻线索指向板块或同行同步波动，说明本轮行情可能不只是单一公司事件。",
    ),
    (
        "macro_risk",
        ("nasdaq", "rates", "yield", "fed", "inflation", "risk-off", "纳指", "利率", "美联储", "通胀", "风险偏好"),
        "宏观风险偏好变化",
        "新闻线索指向宏观或利率背景，需要把个股表现放在市场风险偏好里核验。",
    ),
    (
        "corporate_action",
        ("split", "dividend", "buyback", "merger", "offering", "拆股", "分红", "回购", "并购", "增发"),
        "公司行动背景",
        "新闻线索指向公司行动，需要先排除拆股、分红、回购或融资对价格口径的影响。",
    ),
]


def classify_news_events(facts: list[Fact]) -> list[NewsEvent]:
    """Classify already-normalized news facts without adding new evidence."""

    events: list[NewsEvent] = []
    for fact in facts:
        if fact.metric not in {"news_tone", "unknown_news"}:
            continue
        for title in _news_titles(fact):
            event_type, label, summary = _classify_title(title)
            events.append(
                NewsEvent(
                    event_type=event_type,
                    label=label,
                    summary=summary,
                    supporting_fact_ids=[fact.id],
                    source_titles=[title],
                    confidence="low" if event_type == "unknown" else "medium",
                )
            )
    if events:
        primary_index = next((idx for idx, event in enumerate(events) if event.event_type != "unknown"), 0)
        events[primary_index] = NewsEvent(**{**events[primary_index].__dict__, "is_primary": True})
    return events


def _classify_title(title: str) -> tuple[NewsEventType, str, str]:
    text = title.lower()
    for event_type, keywords, label, summary in _EVENT_RULES:
        if any(_contains_keyword(text, keyword) for keyword in keywords):
            return event_type, label, summary
    return "unknown", "未分类新闻线索", "新闻标题暂时不能归入明确事件类别，不能单独支撑强归因。"


def _contains_keyword(text: str, keyword: str) -> bool:
    lowered = keyword.lower()
    if lowered.isascii() and len(lowered) <= 3:
        return re.search(rf"\b{re.escape(lowered)}\b", text) is not None
    return lowered in text


def _news_titles(fact: Fact) -> list[str]:
    value = fact.value
    if not isinstance(value, dict):
        return []
    if isinstance(value.get("titles"), list):
        return [str(title) for title in value["titles"] if title]
    items = value.get("items") or []
    return [str(item.get("title")) for item in items if isinstance(item, dict) and item.get("title")]

