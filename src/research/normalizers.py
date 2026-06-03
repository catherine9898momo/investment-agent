"""Normalize raw research tool results into traceable sources and facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.research.models import Fact, Source, new_id, utc_now_iso
from src.research.tool_provider import ToolResultBundle


STALE_QUOTE_MAX_AGE_DAYS = 2


@dataclass
class NormalizedToolResult:
    sources: list[Source]
    facts: list[Fact]


def normalize_tool_result_bundle(bundle: ToolResultBundle, symbol: str) -> NormalizedToolResult:
    """Convert one provider bundle into the stable Source/Fact contract."""
    results = [
        normalize_preferences(bundle.preferences, bundle.data_source, symbol),
        normalize_quote(bundle.quote, bundle.data_source, symbol),
        normalize_history(bundle.history, bundle.data_source, symbol),
        normalize_news(bundle.news, bundle.data_source, symbol),
        normalize_corporate_actions(bundle.corporate_actions, bundle.data_source, symbol),
    ]
    normalized = _merge(results)
    quality = normalize_data_quality(bundle, symbol)
    if quality.facts:
        return _merge([normalized, quality])
    return normalized


def normalize_preferences(preferences: dict[str, Any], data_source: str, symbol: str) -> NormalizedToolResult:
    source = _source("user_memory", "User investment preferences", "memory.get_preferences", "high")
    if _has_error(preferences):
        return _failure_result(source, "preferences", "investment_preferences", preferences, symbol)
    return NormalizedToolResult(
        sources=[source],
        facts=[
            _fact(
                f"User preference snapshot: {preferences}",
                source,
                metric="investment_preferences",
                value=preferences,
                symbol=symbol,
            )
        ],
    )


def normalize_quote(quote: dict[str, Any], data_source: str, symbol: str) -> NormalizedToolResult:
    source = _tool_source(data_source, "quote snapshot", "finance.get_quote")
    if _has_error(quote):
        return _failure_result(source, "quote", "latest_price", quote, symbol)
    return NormalizedToolResult(
        sources=[source],
        facts=[
            _fact(
                summarize_quote_fact(symbol, quote),
                source,
                metric="latest_price",
                value=quote,
                symbol=symbol,
            )
        ],
    )


def normalize_history(history: dict[str, Any], data_source: str, symbol: str) -> NormalizedToolResult:
    source = _tool_source(data_source, "price history", "finance.get_history")
    if _has_error(history):
        return _failure_result(source, "history", "five_day_close_range", history, symbol)
    metric = "five_day_close_range" if _valid_history(history) else "unknown_history"
    return NormalizedToolResult(
        sources=[source],
        facts=[
            _fact(
                summarize_history_fact(symbol, history),
                source,
                metric=metric,
                value=history,
                symbol=symbol,
            )
        ],
    )


def normalize_news(news: dict[str, Any], data_source: str, symbol: str) -> NormalizedToolResult:
    source = _tool_source(data_source, "news snapshot", "news.get_news")
    if _has_error(news):
        return _failure_result(source, "news", "news_tone", news, symbol)
    metric = "news_tone" if news.get("items") else "unknown_news"
    return NormalizedToolResult(
        sources=[source],
        facts=[
            _fact(
                summarize_news_fact(news),
                source,
                metric=metric,
                value=news,
                symbol=symbol,
            )
        ],
    )


def normalize_corporate_actions(actions: dict[str, Any], data_source: str, symbol: str) -> NormalizedToolResult:
    source = _tool_source(data_source, "corporate actions", "corporate_actions.get_corporate_actions", "high")
    if _has_error(actions):
        return _failure_result(source, "corporate_actions", "corporate_actions", actions, symbol)
    return NormalizedToolResult(
        sources=[source],
        facts=[
            _fact(
                summarize_actions_fact(symbol, actions),
                source,
                metric="corporate_actions",
                value=actions,
                symbol=symbol,
            )
        ],
    )


def normalize_data_quality(bundle: ToolResultBundle, symbol: str) -> NormalizedToolResult:
    source = _tool_source(bundle.data_source, "data quality checks", "research.data_quality_check")
    facts: list[Fact] = []

    quote_timestamp = _first_present_timestamp(bundle.quote, ["as_of", "timestamp", "last_updated", "fetched_at"])
    if quote_timestamp and _is_older_than_days(quote_timestamp, STALE_QUOTE_MAX_AGE_DAYS):
        facts.append(
            _fact(
                f"Data quality limitation for {symbol}: quote timestamp {quote_timestamp} is stale for current research use.",
                source,
                metric="stale_quote",
                value={"observed_at": quote_timestamp, "max_age_days": STALE_QUOTE_MAX_AGE_DAYS},
                symbol=symbol,
            )
        )

    news_items = bundle.news.get("items") or []
    if _has_error(bundle.news) or not news_items:
        facts.append(
            _fact(
                f"Data quality limitation for {symbol}: news results are missing or unavailable and cannot support fresh news conclusions.",
                source,
                metric="missing_news",
                value={"news": bundle.news},
                symbol=symbol,
            )
        )

    history_direction = _history_direction(bundle.history)
    news_signal = _news_signal(bundle.news)
    if _signals_conflict(history_direction, news_signal):
        facts.append(
            _fact(
                (
                    f"Data quality limitation for {symbol}: recent price history signal "
                    f"({history_direction}) conflicts with news signal ({news_signal})."
                ),
                source,
                metric="conflicting_signals",
                value={"history_direction": history_direction, "news_signal": news_signal},
                symbol=symbol,
            )
        )

    if not facts:
        return NormalizedToolResult(sources=[], facts=[])
    return NormalizedToolResult(sources=[source], facts=facts)


def summarize_quote_fact(symbol: str, quote: dict[str, Any]) -> str:
    return (
        f"{symbol} quote snapshot: price {quote.get('price')} {quote.get('currency')}, "
        f"change {quote.get('change_pct')}% vs previous close."
    )


def summarize_history_fact(symbol: str, history: dict[str, Any]) -> str:
    bars = history.get("bars") or []
    if not bars:
        return f"{symbol} history tool returned no bars."
    closes = [bar.get("close") for bar in bars if bar.get("close") is not None]
    if not closes:
        return f"{symbol} history bars did not include close prices."
    return (
        f"{symbol} {history.get('period')} close range: {min(closes)} to {max(closes)}; "
        f"latest close {closes[-1]}."
    )


def summarize_news_fact(news: dict[str, Any]) -> str:
    items = news.get("items") or []
    if not items:
        return f"News tool returned no recent items for query {news.get('query')}."
    titles = [item.get("title", "") for item in items[:3]]
    return f"Recent news snapshot for {news.get('query')} returned {len(items)} items; top titles: {titles}."


def summarize_actions_fact(symbol: str, actions: dict[str, Any]) -> str:
    return (
        f"{symbol} corporate actions snapshot: splits_count={actions.get('splits_count')}, "
        f"cumulative_split_factor={actions.get('cumulative_split_factor')}, source={actions.get('source')}."
    )


def _merge(results: list[NormalizedToolResult]) -> NormalizedToolResult:
    sources = [source for result in results for source in result.sources]
    facts = [fact for result in results for fact in result.facts]
    return NormalizedToolResult(sources=sources, facts=facts)


def _source(kind: str, name: str, tool_name: str, reliability: str = "medium") -> Source:
    return Source(
        id=new_id("src"),
        kind=kind,  # type: ignore[arg-type]
        name=name,
        tool_name=tool_name,
        fetched_at=utc_now_iso(),
        reliability=reliability,  # type: ignore[arg-type]
    )


def _tool_source(data_source: str, name: str, tool_name: str, reliability: str = "medium") -> Source:
    kind = "local_fixture" if data_source == "fixture" else "tool_result"
    return _source(kind, f"{data_source} {name}", tool_name, reliability)


def _fact(text: str, source: Source, metric: str, value: Any, symbol: str) -> Fact:
    return Fact(
        id=new_id("fact"),
        text=text,
        source_ids=[source.id],
        observed_at=source.fetched_at,
        metric=metric,
        value=value,
        symbol=symbol,
    )


def _failure_result(
    source: Source,
    slot: str,
    expected_metric: str,
    value: dict[str, Any],
    symbol: str,
) -> NormalizedToolResult:
    error = value.get("error") or "unknown tool failure"
    return NormalizedToolResult(
        sources=[source],
        facts=[
            _fact(
                f"{slot} tool returned failure for {symbol}: {error}.",
                source,
                metric=f"failure_{expected_metric}",
                value=value,
                symbol=symbol,
            )
        ],
    )


def _has_error(value: dict[str, Any]) -> bool:
    return bool(value.get("error"))


def _valid_history(history: dict[str, Any]) -> bool:
    bars = history.get("bars") or []
    return any(bar.get("close") is not None for bar in bars)


def _first_present_timestamp(value: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return None


def _is_older_than_days(timestamp: str, days: int) -> bool:
    parsed = _parse_datetime(timestamp)
    if parsed is None:
        return False
    age = datetime.now(timezone.utc) - parsed
    return age.days > days


def _parse_datetime(value: str) -> datetime | None:
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _history_direction(history: dict[str, Any]) -> str:
    bars = history.get("bars") or []
    closes = [bar.get("close") for bar in bars if isinstance(bar.get("close"), int | float)]
    if len(closes) < 2 or closes[0] == 0:
        return "unknown"
    change_pct = ((closes[-1] - closes[0]) / closes[0]) * 100
    if change_pct >= 1:
        return "positive"
    if change_pct <= -1:
        return "negative"
    return "flat"


def _news_signal(news: dict[str, Any]) -> str:
    titles = " ".join(str(item.get("title", "")) for item in news.get("items") or []).lower()
    if not titles:
        return "unknown"
    positive_keywords = ["beat", "growth", "strong", "record", "rally", "positive", "improves", "surge"]
    negative_keywords = ["miss", "weak", "falls", "decline", "concern", "cuts", "probe", "negative", "slump"]
    has_positive = any(keyword in titles for keyword in positive_keywords)
    has_negative = any(keyword in titles for keyword in negative_keywords)
    if has_positive and has_negative:
        return "mixed"
    if has_positive:
        return "positive"
    if has_negative:
        return "negative"
    if "mixed" in titles:
        return "mixed"
    return "unknown"


def _signals_conflict(history_direction: str, news_signal: str) -> bool:
    return (history_direction, news_signal) in {("positive", "negative"), ("negative", "positive")}
