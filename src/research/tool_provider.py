"""Tool result providers for research runs.

The live provider reuses the same backend functions exposed by the MCP servers.
That keeps the research demo lightweight while preserving the tool-result
schemas used by the MCP tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, Literal, Protocol

from src.memory import store
from src.research.models import PeerUniverseItem


@dataclass
class ToolResultBundle:
    data_source: Literal["fixture", "live"]
    preferences: dict[str, Any]
    quote: dict[str, Any]
    history: dict[str, Any]
    news: dict[str, Any]
    corporate_actions: dict[str, Any]
    sector_history: dict[str, Any] = field(default_factory=dict)
    peer_history: dict[str, Any] = field(default_factory=dict)
    analyst_actions: dict[str, Any] = field(default_factory=dict)
    earnings_guidance: dict[str, Any] = field(default_factory=dict)
    macro_context: dict[str, Any] = field(default_factory=dict)


class ToolResultProvider(Protocol):
    data_source: Literal["fixture", "live"]

    def fetch(
        self,
        symbol: str,
        company_query: str,
        history_days: int,
        news_days: int,
        sector_items: list[PeerUniverseItem] | None = None,
        peer_items: list[PeerUniverseItem] | None = None,
    ) -> ToolResultBundle:
        """Return tool-shaped results for one research run."""


class FixtureToolResultProvider:
    data_source: Literal["fixture"] = "fixture"

    def fetch(
        self,
        symbol: str,
        company_query: str,
        history_days: int,
        news_days: int,
        sector_items: list[PeerUniverseItem] | None = None,
        peer_items: list[PeerUniverseItem] | None = None,
    ) -> ToolResultBundle:
        preferences = store.get_all_preferences() or default_preferences()
        return ToolResultBundle(
            data_source=self.data_source,
            preferences=preferences,
            quote={
                "symbol": symbol,
                "price": 94.00,
                "previous_close": 100.00,
                "change_pct": -6.00,
                "currency": "USD",
            },
            history={
                "symbol": symbol,
                "period": "5d",
                "bars": [
                    {"date": "2026-05-26", "close": 100.00},
                    {"date": "2026-05-27", "close": 98.40},
                    {"date": "2026-05-28", "close": 96.80},
                    {"date": "2026-05-29", "close": 95.20},
                    {"date": "2026-06-01", "close": 94.00},
                ],
            },
            news={
                "query": company_query,
                "days": news_days,
                "items": [
                    {
                        "title": f"演示数据：{company_query} 需求与利润率讨论仍偏混合",
                        "source": "Local Demo News",
                        "published": "2026-06-01T12:00:00+00:00",
                        "link": f"local-fixture://news/{symbol.lower()}-mixed-margin",
                    },
                    {
                        "title": f"演示数据：{company_query} 行业需求与竞争仍是关键观察点",
                        "source": "Local Demo News",
                        "published": "2026-05-31T12:00:00+00:00",
                        "link": f"local-fixture://news/{symbol.lower()}-demand-competition",
                    },
                ],
            },
            corporate_actions={
                "symbol": symbol,
                "actions": [
                    {"action_type": "split", "date": "2020-08-31", "ratio": "5:1", "factor": 5.0},
                    {"action_type": "split", "date": "2022-08-25", "ratio": "3:1", "factor": 3.0},
                ],
                "splits_count": 2,
                "cumulative_split_factor": 15.0,
                "source": "local_fixture",
                "last_fetched": "2026-06-01T12:00:00+00:00",
            },
            sector_history=_fixture_comparison_history(sector_items or [], history_days),
            peer_history=_fixture_comparison_history(peer_items or [], history_days),
            analyst_actions={},
            earnings_guidance={},
            macro_context={},
        )


class LiveToolResultProvider:
    data_source: Literal["live"] = "live"

    def fetch(
        self,
        symbol: str,
        company_query: str,
        history_days: int,
        news_days: int,
        sector_items: list[PeerUniverseItem] | None = None,
        peer_items: list[PeerUniverseItem] | None = None,
    ) -> ToolResultBundle:
        """/**
         * 为已解析标的拉取 live 工具结果。
         *
         * @param symbol - 由 intake/entity 层解析出的 ticker。
         * @param company_query - 由 intake/entity 层解析出的公司/新闻 query。
         * @param history_days - planner/caller 请求的价格历史回看窗口。
         * @param news_days - planner/caller 请求的新闻回看窗口。
         * @returns 与 fixture provider 输出形态一致的 ToolResultBundle。
         *
         * @remarks 每个实时工具独立导入和执行，避免某个依赖缺失导致整轮研究
         * 全部失败；失败会进入结构化 failure fact，而不是伪装成 fixture 数据。
         */
        """

        preferences = _safe_tool_result("memory.get_preferences", lambda: store.get_all_preferences() or default_preferences())
        return ToolResultBundle(
            data_source=self.data_source,
            preferences=preferences,
            quote=_safe_tool_result("finance.get_quote", lambda: _live_quote(symbol)),
            history=_safe_tool_result("finance.get_history", lambda: _live_history(symbol, history_days)),
            news=_safe_tool_result("news.get_news", lambda: _live_news(company_query, news_days)),
            corporate_actions=_safe_tool_result("corporate_actions.get_corporate_actions", lambda: _live_corporate_actions(symbol)),
            sector_history=_live_comparison_history(sector_items or [], history_days),
            peer_history=_live_comparison_history(peer_items or [], history_days),
            analyst_actions={},
            earnings_guidance={},
            macro_context={},
        )


def _fixture_comparison_history(items: list[PeerUniverseItem], history_days: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        change_pct = _fixture_change_pct(item.symbol, idx)
        start = 100.0
        end = round(start * (1 + change_pct / 100), 2)
        rows.append({
            "symbol": item.symbol,
            "group": item.group,
            "label": item.label,
            "status": "ok",
            "change_pct": change_pct,
            "bars": [{"date": "2026-05-26", "close": start}, {"date": "2026-06-01", "close": end}],
        })
    return {"period": f"{history_days}d", "items": rows}


def _fixture_change_pct(symbol: str, index: int) -> float:
    memory_moves = {"WDC": -4.2, "STX": -3.8, "SNDK": -4.8}
    if symbol in memory_moves:
        return memory_moves[symbol]
    if symbol in {"SMH", "SOXX", "QQQ", "XLK", "KWEB", "2800.HK", "3067.HK"}:
        return -2.0 - (index * 0.2)
    return -1.0 - (index * 0.3)


def _live_comparison_history(items: list[PeerUniverseItem], history_days: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in items:
        result = _safe_tool_result("finance.get_history", lambda item=item: _live_history(item.symbol, history_days))
        if result.get("error"):
            rows.append({"symbol": item.symbol, "group": item.group, "label": item.label, "status": "error", "error": result.get("error")})
            continue
        rows.append(_comparison_item_from_history(item, result))
    return {"period": f"{history_days}d", "items": rows}


def _comparison_item_from_history(item: PeerUniverseItem, history: dict[str, Any]) -> dict[str, Any]:
    bars = history.get("bars") or []
    closes = [float(bar["close"]) for bar in bars if isinstance(bar, dict) and isinstance(bar.get("close"), (int, float))]
    change_pct = None
    if len(closes) >= 2 and closes[0] != 0:
        change_pct = ((closes[-1] - closes[0]) / closes[0]) * 100
    return {
        "symbol": item.symbol,
        "group": item.group,
        "label": item.label,
        "status": "ok",
        "change_pct": change_pct,
        "bars": bars,
    }


def _live_quote(symbol: str) -> dict[str, Any]:
    from src.mcp_servers.finance_server import _fetch_quote

    return _fetch_quote(symbol)


def _live_history(symbol: str, history_days: int) -> dict[str, Any]:
    from src.mcp_servers.finance_server import _fetch_history

    return _fetch_history(symbol, history_days)


def _live_news(company_query: str, news_days: int) -> dict[str, Any]:
    from src.mcp_servers.news_server import _fetch_news

    return _fetch_news(company_query, news_days, "en")


def _live_corporate_actions(symbol: str) -> dict[str, Any]:
    from src.mcp_servers.corporate_actions_server import get_corporate_actions

    return get_corporate_actions(symbol, include_dividends=False)


def _tool_failure(tool_name: str, reason: str, **params: Any) -> dict[str, Any]:
    return {"error": f"{tool_name} failed: {reason}", "params": params}


def _safe_tool_result(tool_name: str, fetch: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        result = fetch()
    except Exception as exc:  # noqa: BLE001 - keep the research loop alive on individual tool failures.
        return {"error": f"{tool_name} failed: {exc.__class__.__name__}"}
    if isinstance(result, dict):
        return result
    return {"error": f"{tool_name} returned non-dict result: {type(result).__name__}"}


def make_tool_provider(name: str) -> ToolResultProvider:
    if name == "fixture":
        return FixtureToolResultProvider()
    if name == "live":
        return LiveToolResultProvider()
    raise ValueError(f"Unknown data source: {name}")


def default_preferences() -> dict[str, Any]:
    return {
        "style": "价值投资研究优先，避免短线交易建议",
        "risk": "偏好先确认风险和反证，再讨论是否继续研究",
    }
