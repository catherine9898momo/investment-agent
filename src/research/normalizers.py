"""Normalize raw research tool results into traceable sources and facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.research.data_quality import classify_history_points, finite_closes, is_finite_number
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
        normalize_comparison_history(bundle.sector_history, bundle.data_source, symbol, "sector_move", "sector/index moves", "finance.get_history.sector"),
        normalize_comparison_history(bundle.peer_history, bundle.data_source, symbol, "peer_moves", "peer moves", "finance.get_history.peers"),
        normalize_enhanced_company_evidence(bundle.analyst_actions, bundle.data_source, symbol, "analyst_actions", "analyst actions", "research.get_analyst_actions"),
        normalize_enhanced_company_evidence(bundle.earnings_guidance, bundle.data_source, symbol, "earnings_or_guidance", "earnings guidance", "research.get_earnings_guidance"),
        normalize_enhanced_company_evidence(bundle.macro_context, bundle.data_source, symbol, "macro_context", "macro context", "research.get_macro_context"),
    ]
    normalized = _merge(results)
    quality = normalize_data_quality(bundle, symbol)
    if quality.facts:
        return _merge([normalized, quality])
    return normalized




def normalize_global_stock_snapshot(snapshot: dict[str, Any], symbol: str) -> NormalizedToolResult:
    """Convert first-phase global stock data into Source/Fact records."""
    results: list[NormalizedToolResult] = []
    if "fundamentals" in snapshot:
        results.append(_normalize_global_stock_slot(
            snapshot["fundamentals"],
            symbol,
            name="global stock fundamentals",
            tool_name="global_stock.get_fundamentals",
            metric="fundamentals",
            reliability="medium",
            summarize=summarize_fundamentals_fact,
        ))
    if "sec_company_facts" in snapshot:
        results.append(_normalize_global_stock_slot(
            snapshot["sec_company_facts"],
            symbol,
            name="SEC company facts",
            tool_name="global_stock.get_sec_company_facts",
            metric="sec_company_facts",
            reliability="high",
            summarize=summarize_sec_company_facts,
        ))
    if "search" in snapshot:
        results.append(_normalize_global_stock_slot(
            {"results": snapshot["search"]},
            symbol,
            name="global stock search",
            tool_name="global_stock.search_stocks",
            metric="stock_search",
            reliability="medium",
            summarize=summarize_stock_search_fact,
        ))
    if "market_list" in snapshot:
        results.append(_normalize_global_stock_slot(
            {"rows": snapshot["market_list"]},
            symbol,
            name="global stock market list",
            tool_name="global_stock.market_stock_list",
            metric="market_list",
            reliability="medium",
            summarize=summarize_market_list_fact,
        ))
    return _merge(results)


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
    bars = history.get("bars") or []
    closes = finite_closes(bars)
    classification = classify_history_points(closes)
    metric = "five_day_close_range" if classification.usable_for_range else "unknown_history"
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



def normalize_comparison_history(
    comparison: dict[str, Any],
    data_source: str,
    symbol: str,
    metric: str,
    name: str,
    tool_name: str,
) -> NormalizedToolResult:
    source = _tool_source(data_source, name, tool_name)
    items = comparison.get("items") if isinstance(comparison, dict) else None
    if not items:
        return NormalizedToolResult(sources=[], facts=[])
    summary = summarize_comparison_fact(symbol, comparison, metric)
    return NormalizedToolResult(
        sources=[source],
        facts=[_fact(summary, source, metric=metric, value=_comparison_value(comparison), symbol=symbol)],
    )

def normalize_enhanced_company_evidence(
    payload: dict[str, Any],
    data_source: str,
    symbol: str,
    metric: str,
    name: str,
    tool_name: str,
) -> NormalizedToolResult:
    items = payload.get("items") if isinstance(payload, dict) else None
    if not items:
        return NormalizedToolResult(sources=[], facts=[])
    source = _tool_source(data_source, name, tool_name)
    return NormalizedToolResult(
        sources=[source],
        facts=[_fact(summarize_enhanced_company_fact(symbol, payload, metric), source, metric=metric, value=payload, symbol=symbol)],
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

    facts.extend(_quote_quality_facts(bundle.quote, source, symbol))
    facts.extend(_history_quality_facts(bundle.history, source, symbol))
    facts.extend(_corporate_action_quality_facts(bundle, source, symbol))
    facts.extend(_price_provenance_facts(bundle, source, symbol))
    facts.extend(_comparison_quality_facts(bundle, source, symbol))

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
    closes = _finite_closes(bars)
    if not closes:
        return f"{symbol} history bars did not include close prices."
    return (
        f"{symbol} {history.get('period')} close range: {min(closes)} to {max(closes)}; "
        f"latest close {closes[-1]}."
    )


def _finite_closes(bars: list) -> list[float]:
    return finite_closes(bars)



def summarize_comparison_fact(symbol: str, comparison: dict[str, Any], metric: str) -> str:
    value = _comparison_value(comparison)
    label = "sector/index" if metric == "sector_move" else "peer"
    successes = value["items"]
    failures = value["partial_failures"]
    if not successes:
        return f"{symbol} {label} comparison returned no usable symbols; failures={len(failures)}."
    move_text = ", ".join(f"{item['symbol']} {item.get('change_pct')}%" for item in successes[:5])
    return f"{symbol} {label} comparison: {move_text}; partial_failures={len(failures)}."


def _comparison_value(comparison: dict[str, Any]) -> dict[str, Any]:
    raw_items = comparison.get("items") or []
    successes: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        normalized = {
            "symbol": item.get("symbol"),
            "group": item.get("group"),
            "label": item.get("label"),
            "status": item.get("status"),
            "change_pct": item.get("change_pct"),
            "bars": item.get("bars") or [],
        }
        if item.get("status") == "ok" and is_finite_number(item.get("change_pct")):
            successes.append(normalized)
        else:
            failures.append({
                "symbol": item.get("symbol"),
                "group": item.get("group"),
                "label": item.get("label"),
                "status": item.get("status", "error"),
                "error": item.get("error", "missing or invalid change_pct"),
            })
    return {
        "items": successes,
        "partial_failures": failures,
        "success_count": len(successes),
        "failure_count": len(failures),
        "coverage_ratio": len(successes) / len(raw_items) if raw_items else 0.0,
    }

def summarize_enhanced_company_fact(symbol: str, payload: dict[str, Any], metric: str) -> str:
    labels = {
        "analyst_actions": "analyst actions",
        "earnings_or_guidance": "earnings and guidance",
        "macro_context": "macro context",
    }
    items = payload.get("items") or []
    snippets = []
    for item in items[:3]:
        if isinstance(item, dict):
            snippets.append(str(item.get("detail") or item.get("action") or item.get("metric") or item))
    return f"{symbol} {labels.get(metric, metric)} snapshot: {'; '.join(snippets)}."


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



def summarize_fundamentals_fact(symbol: str, fundamentals: dict[str, Any]) -> str:
    rows = fundamentals.get("rows") or []
    if not rows:
        return f"{symbol} fundamentals source returned no indicator rows."
    latest = rows[0]
    return (
        f"{symbol} fundamentals snapshot from {fundamentals.get('source')}: "
        f"report_date={latest.get('report_date')}, roe_avg={latest.get('roe_avg')}, "
        f"basic_eps={latest.get('basic_eps')}, gross_profit_ratio={latest.get('gross_profit_ratio')}."
    )


def summarize_sec_company_facts(symbol: str, company_facts: dict[str, Any]) -> str:
    gaap = ((company_facts.get("facts") or {}).get("us-gaap")) or {}
    return (
        f"{symbol} SEC company facts snapshot: cik={company_facts.get('cik')}, "
        f"entity={company_facts.get('entity_name')}, gaap_metrics={len(gaap)}."
    )


def summarize_stock_search_fact(search: dict[str, Any]) -> str:
    results = search.get("results") or []
    symbols = [item.get("symbol") for item in results[:5] if isinstance(item, dict)]
    return f"Stock search returned {len(results)} candidates; top symbols: {symbols}."


def summarize_market_list_fact(market_list: dict[str, Any]) -> str:
    rows = market_list.get("rows") or []
    symbols = [item.get("symbol") for item in rows[:5] if isinstance(item, dict)]
    return f"Market list returned {len(rows)} rows; top symbols: {symbols}."


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



def _normalize_global_stock_slot(
    value: Any,
    symbol: str,
    name: str,
    tool_name: str,
    metric: str,
    reliability: str,
    summarize: Any,
) -> NormalizedToolResult:
    source = _source("tool_result", name, tool_name, reliability)
    if not isinstance(value, dict):
        value = {"error": f"unexpected payload type: {type(value).__name__}", "raw": value}
    if _has_error(value):
        return _failure_result(source, name, metric, value, symbol)
    if metric in {"stock_search", "market_list"}:
        text = summarize(value)
    else:
        text = summarize(symbol, value)
    return NormalizedToolResult(
        sources=[source],
        facts=[_fact(text, source, metric, value, symbol)],
    )





def _comparison_quality_facts(bundle: ToolResultBundle, source: Source, symbol: str) -> list[Fact]:
    facts: list[Fact] = []
    for label, comparison in (("sector", bundle.sector_history), ("peer", bundle.peer_history)):
        value = _comparison_value(comparison) if comparison else {"success_count": 0, "failure_count": 0}
        if value["failure_count"] > 0:
            facts.append(_fact(
                f"Data quality limitation for {symbol}: {label} comparison has {value['failure_count']} partial symbol failures.",
                source,
                metric="data_quality_sector_peer_partial",
                value={"comparison_type": label, **value},
                symbol=symbol,
            ))
    return facts

def _quote_quality_facts(quote: dict[str, Any], source: Source, symbol: str) -> list[Fact]:
    facts: list[Fact] = []
    fields = [
        ("price", "data_quality_invalid_quote_price"),
        ("previous_close", "data_quality_invalid_previous_close"),
        ("change_pct", "data_quality_invalid_change_pct"),
    ]
    for field, metric in fields:
        value = quote.get(field)
        if value is not None and not is_finite_number(value):
            facts.append(_fact(
                f"Data quality limitation for {symbol}: quote field {field} is not a finite number.",
                source,
                metric=metric,
                value={"field": field, "raw_value": value},
                symbol=symbol,
            ))

    price = quote.get("price")
    previous_close = quote.get("previous_close")
    change_pct = quote.get("change_pct")
    if is_finite_number(price) and is_finite_number(previous_close) and is_finite_number(change_pct) and float(previous_close) != 0:
        computed = ((float(price) - float(previous_close)) / float(previous_close)) * 100
        if abs(computed - float(change_pct)) > 0.25:
            facts.append(_fact(
                (
                    f"Data quality limitation for {symbol}: quote change_pct {change_pct} does not match "
                    f"price {price} and previous_close {previous_close}; computed change is {computed:.2f}%."
                ),
                source,
                metric="data_quality_quote_change_mismatch",
                value={"price": price, "previous_close": previous_close, "reported_change_pct": change_pct, "computed_change_pct": computed},
                symbol=symbol,
            ))
    return facts


def _history_quality_facts(history: dict[str, Any], source: Source, symbol: str) -> list[Fact]:
    if _has_error(history):
        return []
    bars = history.get("bars") or []
    closes = _finite_closes(bars)
    classification = classify_history_points(closes)
    if not classification.usable_for_range:
        return [
            _fact(
                (
                    f"Data quality limitation for {symbol}: only {classification.valid_close_count} valid history close "
                    "was available; cannot compute a close range or trend."
                ),
                source,
                metric="data_quality_history_insufficient",
                value={
                    "valid_close_count": classification.valid_close_count,
                    "required_for_range": 2,
                    "required_for_trend": 3,
                },
                symbol=symbol,
            )
        ]
    if not classification.window_complete:
        return [
            _fact(
                (
                    f"Data quality limitation for {symbol}: history window is incomplete with "
                    f"{classification.valid_close_count} valid closes; trend language should be limited."
                ),
                source,
                metric="data_quality_history_window_incomplete",
                value={
                    "valid_close_count": classification.valid_close_count,
                    "requested_close_count": classification.requested_close_count,
                    "usable_for_trend": classification.usable_for_trend,
                },
                symbol=symbol,
            )
        ]
    return []


def _corporate_action_quality_facts(bundle: ToolResultBundle, source: Source, symbol: str) -> list[Fact]:
    if _has_error(bundle.corporate_actions):
        return []
    actions = bundle.corporate_actions.get("actions") or []
    window_actions = _actions_in_history_window(actions, bundle.history)
    if not window_actions or _has_adjustment_metadata(bundle.quote, bundle.history):
        return []
    return [
        _fact(
            (
                f"Data quality limitation for {symbol}: corporate action exists inside the research window, "
                "but quote/history adjustment metadata is unavailable."
            ),
            source,
            metric="data_quality_corporate_action_adjustment_uncertain",
            value={"actions_in_window": window_actions, "provenance_status": "uncertain"},
            symbol=symbol,
        )
    ]


def _price_provenance_facts(bundle: ToolResultBundle, source: Source, symbol: str) -> list[Fact]:
    price = bundle.quote.get("price")
    closes = _finite_closes(bundle.history.get("bars") or [])
    if not is_finite_number(price) or len(closes) < 2:
        return []
    latest_close = closes[-1]
    mean_close = sum(closes) / len(closes)
    latest_deviation = _pct_deviation(float(price), latest_close)
    mean_deviation = _pct_deviation(float(price), mean_close)
    if latest_deviation <= 5 and mean_deviation <= 20:
        return []
    metric = "price_provenance_uncertain"
    text = (
        f"Data quality limitation for {symbol}: quote price {price} is unusually far from recent history "
        f"(latest deviation {latest_deviation:.2f}%, mean deviation {mean_deviation:.2f}%); provenance needs review."
    )
    if _actions_in_history_window(bundle.corporate_actions.get("actions") or [], bundle.history) and not _has_adjustment_metadata(bundle.quote, bundle.history):
        metric = "conflicting_price_sources"
        text = (
            f"Data quality limitation for {symbol}: quote/history price relationship is abnormal and a corporate action "
            "inside the window has unknown adjustment metadata."
        )
    return [
        _fact(
            text,
            source,
            metric=metric,
            value={
                "price": price,
                "latest_history_close": latest_close,
                "history_mean_close": mean_close,
                "latest_deviation_pct": latest_deviation,
                "mean_deviation_pct": mean_deviation,
                "provenance_status": "conflicting" if metric == "conflicting_price_sources" else "uncertain",
            },
            symbol=symbol,
        )
    ]


def _pct_deviation(value: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0
    return abs((value - baseline) / baseline) * 100


def _actions_in_history_window(actions: list[Any], history: dict[str, Any]) -> list[dict[str, Any]]:
    bars = history.get("bars") or []
    dates = [bar.get("date") for bar in bars if isinstance(bar, dict) and isinstance(bar.get("date"), str)]
    if not dates:
        return []
    start, end = min(dates), max(dates)
    in_window: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_date = action.get("date")
        if isinstance(action_date, str) and start <= action_date <= end:
            in_window.append(action)
    return in_window


def _has_adjustment_metadata(quote: dict[str, Any], history: dict[str, Any]) -> bool:
    keys = {
        "adjusted",
        "auto_adjust",
        "is_adjusted",
        "adjustment",
        "adjustment_policy",
        "price_adjustment",
        "adjusted_close",
    }
    if any(key in quote for key in keys):
        return True
    if any(key in history for key in keys):
        return True
    bars = history.get("bars") or []
    return any(isinstance(bar, dict) and any(key in bar for key in keys) for bar in bars)

def _has_error(value: dict[str, Any]) -> bool:
    return bool(value.get("error"))


def _valid_history(history: dict[str, Any]) -> bool:
    bars = history.get("bars") or []
    return classify_history_points(_finite_closes(bars)).usable_for_range


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
    closes = _finite_closes(bars)
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
