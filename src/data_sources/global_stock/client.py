"""HTTP adapters for first-phase US/HK global stock data.

The functions in this module intentionally return plain dictionaries. Research
code converts those dictionaries into Source/Fact objects before synthesis.
"""

from __future__ import annotations

from typing import Any

import requests


DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_SEC_USER_AGENT = "investment-agent contact@example.com"


def normalize_hk_symbol(symbol: str) -> str:
    """Normalize 5-digit HK symbols to yfinance-compatible 4-digit symbols."""
    if not symbol:
        return symbol
    upper = symbol.upper()
    if upper.endswith(".HK"):
        code, suffix = upper.rsplit(".", 1)
        if len(code) == 5 and code.startswith("0"):
            return f"{code[1:]}.{suffix}"
        return upper
    return upper


class GlobalStockClient:
    """Small client for the phase-one endpoints we want from global-stock-data."""

    EASTMONEY_SEARCH_URL = "https://searchapi.eastmoney.com/api/suggest/get"
    EASTMONEY_CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
    EASTMONEY_INDICATOR_URL = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
    SEC_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

    def __init__(
        self,
        session: Any | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        sec_user_agent: str = DEFAULT_SEC_USER_AGENT,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.sec_user_agent = sec_user_agent

    def search_stocks(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        response = self.session.get(
            self.EASTMONEY_SEARCH_URL,
            params={"keyword": query, "type": "14", "pageindex": "1", "pagesize": str(limit)},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        rows = (((payload.get("QuotationCodeTable") or {}).get("Data")) or [])[:limit]
        return [_normalize_search_row(row) for row in rows if isinstance(row, dict)]

    def market_stock_list(self, market: str, limit: int = 50) -> list[dict[str, Any]]:
        response = self.session.get(
            self.EASTMONEY_CLIST_URL,
            params={
                "pn": "1",
                "pz": str(limit),
                "po": "1",
                "np": "1",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": "2",
                "invt": "2",
                "fid": "f3",
                "fs": _market_fs(market),
                "fields": "f12,f14,f2,f3,f6,f20,f21,f8,f9,f23",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json().get("data") or {}
        return [_normalize_market_row(row, market) for row in _normalize_diff_rows(data.get("diff"))[:limit]]

    def get_fundamentals(self, symbol: str, limit: int = 8) -> dict[str, Any]:
        normalized = normalize_hk_symbol(symbol)
        response = self.session.get(
            self.EASTMONEY_INDICATOR_URL,
            params={
                "reportName": "RPT_HKF10_FN_GMAININDICATOR",
                "columns": "ALL",
                "quoteColumns": "",
                "filter": f'(SECURITY_CODE="{normalized.replace(".HK", "")}")',
                "pageNumber": "1",
                "pageSize": str(limit),
                "sortTypes": "-1",
                "sortColumns": "REPORT_DATE",
                "source": "F10",
                "client": "PC",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        rows = ((response.json().get("result") or {}).get("data")) or []
        return {
            "symbol": normalized,
            "source": "eastmoney_gmainindicator",
            "rows": [_normalize_indicator_row(row) for row in rows if isinstance(row, dict)],
        }

    def get_sec_company_facts(self, symbol: str) -> dict[str, Any]:
        cik = self._lookup_cik(symbol)
        facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        response = self.session.get(
            facts_url,
            headers={"User-Agent": self.sec_user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return {
            "symbol": symbol.upper(),
            "source": "sec_companyfacts",
            "cik": cik,
            "entity_name": payload.get("entityName"),
            "facts": payload.get("facts") or {},
        }

    def _lookup_cik(self, symbol: str) -> str:
        response = self.session.get(
            self.SEC_TICKER_MAP_URL,
            headers={"User-Agent": self.sec_user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        target = symbol.upper().replace(".HK", "")
        for row in response.json().values():
            if isinstance(row, dict) and str(row.get("ticker", "")).upper() == target:
                return str(row.get("cik_str")).zfill(10)
        raise ValueError(f"No SEC CIK mapping found for {symbol}")


def _market_fs(market: str) -> str:
    normalized = market.lower()
    if normalized in {"hk", "hongkong", "hong_kong"}:
        return "m:128+t:3,m:128+t:4"
    if normalized in {"us", "usa", "nasdaq", "nyse", "amex"}:
        return "m:105,m:106,m:107"
    raise ValueError(f"Unsupported market: {market}")


def _normalize_diff_rows(diff: Any) -> list[dict[str, Any]]:
    if isinstance(diff, list):
        return [row for row in diff if isinstance(row, dict)]
    if isinstance(diff, dict):
        return [row for _, row in sorted(diff.items()) if isinstance(row, dict)]
    return []


def _normalize_search_row(row: dict[str, Any]) -> dict[str, Any]:
    code = str(row.get("Code") or row.get("code") or "").upper()
    quote_id = str(row.get("QuoteID") or row.get("quoteId") or "")
    market = _market_from_quote_id(quote_id)
    return {
        "symbol": _symbol_for_market(code, market),
        "name": row.get("Name") or row.get("name"),
        "market": market,
        "secid": quote_id or None,
        "security_type": row.get("SecurityTypeName") or row.get("securityTypeName"),
    }


def _normalize_market_row(row: dict[str, Any], market: str) -> dict[str, Any]:
    market_code = "HK" if market.lower().startswith("hk") else "US"
    code = str(row.get("f12") or "").upper()
    return {
        "symbol": _symbol_for_market(code, market_code),
        "name": row.get("f14"),
        "market": market_code,
        "latest_price": row.get("f2"),
        "change_pct": row.get("f3"),
        "amount": row.get("f6"),
        "market_cap": row.get("f20"),
        "float_market_cap": row.get("f21"),
        "turnover_rate": row.get("f8"),
        "pe": row.get("f9"),
        "pb": row.get("f23"),
    }


def _normalize_indicator_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_date": row.get("REPORT_DATE"),
        "roe_avg": row.get("ROE_AVG"),
        "basic_eps": row.get("BASIC_EPS"),
        "gross_profit_ratio": row.get("GROSS_PROFIT_RATIO"),
        "debt_asset_ratio": row.get("DEBT_ASSET_RATIO"),
        "raw": row,
    }


def _market_from_quote_id(quote_id: str) -> str:
    if quote_id.startswith("116."):
        return "HK"
    if quote_id.startswith(("105.", "106.", "107.")):
        return "US"
    return "UNKNOWN"


def _symbol_for_market(code: str, market: str) -> str:
    if market == "HK" and code and not code.endswith(".HK"):
        return f"{code}.HK"
    return code
