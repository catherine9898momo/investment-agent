"""Tool result providers for research runs.

The live provider reuses the same backend functions exposed by the MCP servers.
That keeps the research demo lightweight while preserving the tool-result
schemas used by the MCP tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any, Literal, Protocol

from src.memory import store


@dataclass
class ToolResultBundle:
    data_source: Literal["fixture", "live"]
    preferences: dict[str, Any]
    quote: dict[str, Any]
    history: dict[str, Any]
    news: dict[str, Any]
    corporate_actions: dict[str, Any]


class ToolResultProvider(Protocol):
    data_source: Literal["fixture", "live"]

    def fetch(self, symbol: str, company_query: str, history_days: int, news_days: int) -> ToolResultBundle:
        """Return tool-shaped results for one research run."""


class FixtureToolResultProvider:
    data_source: Literal["fixture"] = "fixture"

    def fetch(self, symbol: str, company_query: str, history_days: int, news_days: int) -> ToolResultBundle:
        preferences = store.get_all_preferences() or default_preferences()
        return ToolResultBundle(
            data_source=self.data_source,
            preferences=preferences,
            quote={
                "symbol": symbol,
                "price": 182.50,
                "previous_close": 179.30,
                "change_pct": 1.78,
                "currency": "USD",
            },
            history={
                "symbol": symbol,
                "period": "5d",
                "bars": [
                    {"date": "2026-05-26", "close": 176.20},
                    {"date": "2026-05-27", "close": 178.90},
                    {"date": "2026-05-28", "close": 181.10},
                    {"date": "2026-05-29", "close": 179.30},
                    {"date": "2026-06-01", "close": 182.50},
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
        )


class LiveToolResultProvider:
    data_source: Literal["live"] = "live"

    def fetch(self, symbol: str, company_query: str, history_days: int, news_days: int) -> ToolResultBundle:
        """/**
         * 为已解析标的拉取 live 工具结果。
         *
         * @param symbol - 由 intake/entity 层解析出的 ticker。
         * @param company_query - 由 intake/entity 层解析出的公司/新闻 query。
         * @param history_days - planner/caller 请求的价格历史回看窗口。
         * @param news_days - planner/caller 请求的新闻回看窗口。
         * @returns 与 fixture provider 输出形态一致的 ToolResultBundle。
         *
         * @remarks 实时 MCP 后端依赖会保留在这个方法内部导入；这样 fixture 研究 run 即使不安装网络/实时数据依赖，也能验证查询入口、研究计划、报告渲染和 guardrail。
         */
        """

        from src.mcp_servers.corporate_actions_server import get_corporate_actions
        from src.mcp_servers.finance_server import _fetch_history, _fetch_quote
        from src.mcp_servers.news_server import _fetch_news

        preferences = _safe_tool_result("memory.get_preferences", lambda: store.get_all_preferences() or default_preferences())
        return ToolResultBundle(
            data_source=self.data_source,
            preferences=preferences,
            quote=_safe_tool_result("finance.get_quote", lambda: _fetch_quote(symbol)),
            history=_safe_tool_result("finance.get_history", lambda: _fetch_history(symbol, history_days)),
            news=_safe_tool_result("news.get_news", lambda: _fetch_news(company_query, news_days, "en")),
            corporate_actions=_safe_tool_result(
                "corporate_actions.get_corporate_actions",
                lambda: get_corporate_actions(symbol, include_dividends=False),
            ),
        )


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
