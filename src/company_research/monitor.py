"""Generate company research monitoring reports.

This module turns a company research pack into repeatable monitoring output.
It intentionally starts small: a static company pack plus optional live quote,
history, and news from the existing tool backends.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPANY_RESEARCH_DIR = PROJECT_ROOT / "company_research"

DataSource = Literal["fixture", "live"]


@dataclass
class CompanyPack:
    symbol: str
    path: Path
    config: dict[str, Any]

    @property
    def company(self) -> dict[str, Any]:
        return dict(self.config.get("company", {}))

    @property
    def static_snapshot(self) -> dict[str, Any]:
        return dict(self.config.get("static_snapshot", {}))

    @property
    def monitoring_table(self) -> list[dict[str, Any]]:
        rows = self.config.get("monitoring_table", [])
        return rows if isinstance(rows, list) else []


def load_company_pack(symbol: str, base_dir: Path = COMPANY_RESEARCH_DIR) -> CompanyPack:
    normalized = symbol.upper()
    pack_dir = base_dir / normalized
    config_path = pack_dir / "monitoring.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing company monitoring config: {config_path}")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return CompanyPack(symbol=normalized, path=pack_dir, config=config)


def collect_monitoring_data(pack: CompanyPack, data_source: DataSource) -> dict[str, Any]:
    company = pack.company
    symbol = str(company.get("symbol") or pack.symbol)
    company_query = str(company.get("company_query") or company.get("name") or symbol)
    reporting = pack.config.get("reporting", {})
    history_days = int(reporting.get("default_history_days", 10))
    news_days = int(reporting.get("default_news_days", 7))

    if data_source == "live":
        tool_results = collect_live_tool_results(symbol, company_query, history_days, news_days)
    else:
        tool_results = collect_fixture_tool_results(pack)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": data_source,
        "company": company,
        "static_snapshot": pack.static_snapshot,
        "monitoring_table": pack.monitoring_table,
        "tool_results": tool_results,
        "source_notes": pack.config.get("source_notes", []),
    }


def collect_fixture_tool_results(pack: CompanyPack) -> dict[str, Any]:
    """Return offline tool-shaped data from the company pack itself."""
    snapshot = pack.static_snapshot
    price_context = snapshot.get("price_context", {}) if isinstance(snapshot.get("price_context"), dict) else {}
    symbol = pack.company.get("symbol", pack.symbol)
    as_of = snapshot.get("as_of", "unknown")
    observed_price = price_context.get("observed_price")
    observed_change_pct = price_context.get("observed_change_pct")
    fyq2 = snapshot.get("fy2026_q2", {}) if isinstance(snapshot.get("fy2026_q2"), dict) else {}

    return {
        "quote": {
            "symbol": symbol,
            "price": observed_price,
            "previous_close": None,
            "change_pct": observed_change_pct,
            "currency": "USD",
            "source": "company_pack_static_snapshot",
        },
        "history": {
            "symbol": symbol,
            "period": "static",
            "bars": [
                {
                    "date": as_of,
                    "close": observed_price,
                    "volume": "",
                }
            ],
        },
        "news": {
            "query": pack.company.get("company_query", symbol),
            "days": 0,
            "items": [],
            "note": "Fixture mode does not fetch live news.",
        },
        "corporate_actions": {
            "symbol": symbol,
            "actions": [],
            "source": "not_fetched_in_fixture_mode",
        },
        "fundamentals": {
            "fy2026_q2": fyq2,
        },
    }


def collect_live_tool_results(symbol: str, company_query: str, history_days: int, news_days: int) -> dict[str, Any]:
    """Fetch live tool-shaped data, keeping optional dependencies lazy."""
    from src.research.tool_provider import LiveToolResultProvider

    bundle = LiveToolResultProvider().fetch(
        symbol=symbol,
        company_query=company_query,
        history_days=history_days,
        news_days=news_days,
    )
    return {
        "quote": bundle.quote,
        "history": bundle.history,
        "news": bundle.news,
        "corporate_actions": bundle.corporate_actions,
    }


def render_report(payload: dict[str, Any]) -> str:
    company = payload["company"]
    snapshot = payload.get("static_snapshot", {})
    quote = payload["tool_results"].get("quote", {})
    history = payload["tool_results"].get("history", {})
    news = payload["tool_results"].get("news", {})

    lines = [
        f"# {company.get('name', company.get('symbol'))} ({company.get('symbol')}) Monitoring Report",
        "",
        "## Boundary",
        "",
        "This is a repeatable company monitoring report, not investment advice or a trading instruction.",
        "",
        "## Run Metadata",
        "",
        f"- Generated at: {payload['generated_at']}",
        f"- Data source: {payload['data_source']}",
        f"- Next earnings date: {snapshot.get('next_earnings_date', 'unknown')}",
        "",
        "## Market Snapshot",
        "",
        *market_snapshot_lines(snapshot, quote),
        "",
        "## Thesis Monitor",
        "",
        *monitoring_table_lines(payload.get("monitoring_table", [])),
        "",
        "## Price History",
        "",
        *history_lines(history),
        "",
        "## Recent News",
        "",
        *news_lines(news),
        "",
        "## Source Notes",
        "",
        *source_note_lines(payload.get("source_notes", [])),
        "",
        "## Analyst Questions For Next Update",
        "",
        "- Did new data strengthen or weaken the original thesis?",
        "- Is the market reaction explained by fundamentals, expectations, positioning, or industry sympathy moves?",
        "- Did any falsification condition move from watch item to active risk?",
    ]
    return "\n".join(lines)


def market_snapshot_lines(snapshot: dict[str, Any], quote: dict[str, Any]) -> list[str]:
    price_context = snapshot.get("price_context", {}) if isinstance(snapshot.get("price_context"), dict) else {}
    fyq2 = snapshot.get("fy2026_q2", {}) if isinstance(snapshot.get("fy2026_q2"), dict) else {}
    fyq3 = snapshot.get("fy2026_q3_guide", {}) if isinstance(snapshot.get("fy2026_q3_guide"), dict) else {}

    rows = [
        ("Live/fixture price", quote.get("price")),
        ("Live/fixture change pct", quote.get("change_pct")),
        ("Observed price context", price_context.get("observed_price")),
        ("Observed market cap", price_context.get("observed_market_cap")),
        ("Forward PE", price_context.get("forward_pe")),
        ("Trailing PE", price_context.get("trailing_pe")),
        ("FY2026 Q2 revenue ($B)", fyq2.get("revenue_b")),
        ("FY2026 Q2 non-GAAP gross margin", pct(fyq2.get("non_gaap_gross_margin_pct"))),
        ("FY2026 Q2 non-GAAP EPS", fyq2.get("non_gaap_eps")),
        ("FY2026 Q2 adjusted FCF ($B)", fyq2.get("adjusted_free_cash_flow_b")),
        ("FY2026 Q3 revenue guide ($B)", fyq3.get("revenue_b")),
        ("FY2026 Q3 gross margin guide", pct(fyq3.get("gross_margin_pct"))),
        ("FY2026 Q3 non-GAAP EPS guide", fyq3.get("non_gaap_eps")),
    ]
    return markdown_kv_table(rows)


def monitoring_table_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- No monitoring rows configured."]
    lines = [
        "| ID | Category | Metric | Current Status | Positive Signal | Negative Signal | Severity |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{cell(row.get('id'))} | "
            f"{cell(row.get('category'))} | "
            f"{cell(row.get('metric'))} | "
            f"{cell(row.get('current_status'))} | "
            f"{cell(row.get('signal_if_positive'))} | "
            f"{cell(row.get('signal_if_negative'))} | "
            f"{cell(row.get('severity'))} |"
        )
    return lines


def history_lines(history: dict[str, Any]) -> list[str]:
    if history.get("error"):
        return [f"- History unavailable: {history['error']}"]
    bars = history.get("bars") or []
    if not bars:
        return ["- No price history available."]
    lines = ["| Date | Close | Volume |", "|---|---:|---:|"]
    for bar in bars[-10:]:
        date = cell(bar.get("date"))
        close = cell(bar.get("close"))
        volume = cell(bar.get("volume", ""))
        lines.append(f"| {date} | {close} | {volume} |")
    return lines


def news_lines(news: dict[str, Any]) -> list[str]:
    if news.get("error"):
        return [f"- News unavailable: {news['error']}"]
    items = news.get("items") or []
    if not items:
        return ["- No recent news returned."]
    lines = []
    for item in items[:10]:
        title = item.get("title", "Untitled")
        source = item.get("source", "unknown source")
        published = item.get("published", "unknown date")
        link = item.get("link", "")
        if link:
            lines.append(f"- [{title}]({link}) | {source} | {published}")
        else:
            lines.append(f"- {title} | {source} | {published}")
    return lines


def source_note_lines(notes: list[Any]) -> list[str]:
    if not notes:
        return ["- No source notes configured."]
    return [f"- {note}" for note in notes]


def markdown_kv_table(rows: list[tuple[str, Any]]) -> list[str]:
    lines = ["| Metric | Value |", "|---|---:|"]
    lines.extend(f"| {cell(label)} | {cell(value)} |" for label, value in rows)
    return lines


def write_outputs(
    pack: CompanyPack,
    payload: dict[str, Any],
    report: str,
    output_dir: Path | None,
) -> dict[str, Path]:
    target_dir = output_dir or pack.path / "reports"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_name = f"{pack.symbol}_{stamp}_{payload['data_source']}"
    markdown_path = target_dir / f"{base_name}.md"
    json_path = target_dir / f"{base_name}.json"
    markdown_path.write_text(report, encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"markdown": markdown_path, "json": json_path}


def pct(value: Any) -> str:
    if value is None:
        return "unknown"
    return f"{value}%"


def cell(value: Any) -> str:
    if value is None:
        return "unknown"
    return str(value).replace("|", "\\|").replace("\n", " ")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a company monitoring report.")
    parser.add_argument("symbol", help="Company ticker, for example MU.")
    parser.add_argument(
        "--data-source",
        choices=["fixture", "live"],
        default="fixture",
        help="Use fixture for offline output or live for quote/history/news tool backends.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output directory. Defaults to company_research/<SYMBOL>/reports.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pack = load_company_pack(args.symbol)
    payload = collect_monitoring_data(pack, args.data_source)
    report = render_report(payload)
    paths = write_outputs(pack, payload, report, args.output_dir)
    print(f"markdown={paths['markdown']}")
    print(f"json={paths['json']}")


if __name__ == "__main__":
    main()
