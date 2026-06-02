"""Tool result providers for research runs.

The live provider reuses the same backend functions exposed by the MCP servers.
That keeps the research demo lightweight while preserving the tool-result
schemas used by the MCP tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from src.mcp_servers.corporate_actions_server import get_corporate_actions
from src.mcp_servers.finance_server import _fetch_history, _fetch_quote
from src.mcp_servers.news_server import _fetch_news
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
                        "title": "Demo fixture: Tesla delivery and margin discussion remains mixed",
                        "source": "Local Demo News",
                        "published": "2026-06-01T12:00:00+00:00",
                        "link": "local-fixture://news/tesla-mixed-margin",
                    },
                    {
                        "title": "Demo fixture: EV demand and competition remain key watch points",
                        "source": "Local Demo News",
                        "published": "2026-05-31T12:00:00+00:00",
                        "link": "local-fixture://news/ev-demand-competition",
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
        preferences = store.get_all_preferences() or default_preferences()
        return ToolResultBundle(
            data_source=self.data_source,
            preferences=preferences,
            quote=_fetch_quote(symbol),
            history=_fetch_history(symbol, history_days),
            news=_fetch_news(company_query, news_days, "en"),
            corporate_actions=get_corporate_actions(symbol, include_dividends=False),
        )


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
