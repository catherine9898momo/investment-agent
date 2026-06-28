"""Derive enhanced company evidence from live-shaped news and market payloads."""

from __future__ import annotations

from typing import Any


_ANALYST_KEYWORDS = ("analyst", "rating", "upgrade", "downgrade", "price target", "target hiked", "target cut", "目标价", "评级", "分析师")
_EARNINGS_KEYWORDS = ("earnings", "guidance", "outlook", "revenue", "eps", "margin", "profit", "财报", "指引", "营收", "利润率")


def extract_analyst_actions(news: dict[str, Any]) -> dict[str, Any]:
    return {"items": [_news_item_payload(item, "analyst_action") for item in _matching_news_items(news, _ANALYST_KEYWORDS)]}


def extract_earnings_guidance(news: dict[str, Any]) -> dict[str, Any]:
    return {"items": [_news_item_payload(item, "earnings_or_guidance") for item in _matching_news_items(news, _EARNINGS_KEYWORDS)]}


def extract_macro_context(sector_history: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for item in sector_history.get("items") or []:
        if not isinstance(item, dict) or item.get("status") not in {None, "ok"}:
            continue
        change = item.get("change_pct")
        if not isinstance(change, (int, float)):
            continue
        symbol = str(item.get("symbol") or "")
        label = str(item.get("label") or item.get("group") or symbol)
        items.append({
            "symbol": symbol,
            "label": label,
            "change_pct": float(change),
            "detail": f"{symbol} 5d change {float(change):.2f}%",
        })
    return {"items": items}


def _matching_news_items(news: dict[str, Any], keywords: tuple[str, ...]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in news.get("items") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        title_lower = title.lower()
        if any(keyword.lower() in title_lower for keyword in keywords):
            matches.append(item)
    return matches


def _news_item_payload(item: dict[str, Any], metric: str) -> dict[str, Any]:
    title = str(item.get("title") or "")
    return {
        "metric": metric,
        "source": str(item.get("source") or item.get("publisher") or "live news"),
        "published": item.get("published") or item.get("published_at"),
        "url": item.get("link") or item.get("url"),
        "detail": title,
    }
