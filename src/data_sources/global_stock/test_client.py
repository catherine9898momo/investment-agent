from src.data_sources.global_stock.client import GlobalStockClient, normalize_hk_symbol


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None, dict | None]] = []
        self.responses: dict[str, FakeResponse] = {}

    def get(self, url: str, params: dict | None = None, headers: dict | None = None, timeout: int | None = None) -> FakeResponse:
        self.calls.append((url, params, headers))
        key = url.split("?")[0]
        return self.responses[key]


def test_normalize_hk_symbol_removes_yahoo_incompatible_leading_zero() -> None:
    assert normalize_hk_symbol("00700.HK") == "0700.HK"
    assert normalize_hk_symbol("09988.HK") == "9988.HK"
    assert normalize_hk_symbol("AAPL") == "AAPL"


def test_search_stocks_maps_eastmoney_payload_to_stable_results() -> None:
    session = FakeSession()
    session.responses[GlobalStockClient.EASTMONEY_SEARCH_URL] = FakeResponse(
        {
            "QuotationCodeTable": {
                "Data": [
                    {"Code": "00700", "Name": "腾讯控股", "SecurityTypeName": "港股", "QuoteID": "116.00700"},
                    {"Code": "AAPL", "Name": "苹果", "SecurityTypeName": "美股", "QuoteID": "105.AAPL"},
                ]
            }
        }
    )

    results = GlobalStockClient(session=session).search_stocks("腾讯")

    assert results[0]["symbol"] == "00700.HK"
    assert results[0]["secid"] == "116.00700"
    assert results[0]["market"] == "HK"
    assert results[1]["symbol"] == "AAPL"
    assert session.calls[0][1]["keyword"] == "腾讯"


def test_market_stock_list_normalizes_diff_dict_and_passes_params() -> None:
    session = FakeSession()
    session.responses[GlobalStockClient.EASTMONEY_CLIST_URL] = FakeResponse(
        {
            "data": {
                "diff": {
                    "0": {"f12": "AAPL", "f14": "苹果", "f2": 201.0, "f3": 1.2, "f6": 123456},
                    "1": {"f12": "MSFT", "f14": "微软", "f2": 410.0, "f3": -0.5, "f6": 456789},
                }
            }
        }
    )

    rows = GlobalStockClient(session=session).market_stock_list("us", limit=2)

    assert [row["symbol"] for row in rows] == ["AAPL", "MSFT"]
    assert rows[0]["name"] == "苹果"
    assert rows[0]["latest_price"] == 201.0
    assert rows[0]["amount"] == 123456
    assert session.calls[0][1]["pn"] == "1"
    assert session.calls[0][1]["pz"] == "2"


def test_fundamentals_combines_eastmoney_indicator_rows() -> None:
    session = FakeSession()
    session.responses[GlobalStockClient.EASTMONEY_INDICATOR_URL] = FakeResponse(
        {
            "result": {
                "data": [
                    {
                        "SECURITY_CODE": "AAPL",
                        "REPORT_DATE": "2026-03-31",
                        "ROE_AVG": 1.23,
                        "BASIC_EPS": 2.1,
                        "GROSS_PROFIT_RATIO": 44.0,
                        "DEBT_ASSET_RATIO": 55.0,
                    }
                ]
            }
        }
    )

    result = GlobalStockClient(session=session).get_fundamentals("AAPL")

    assert result["symbol"] == "AAPL"
    assert result["source"] == "eastmoney_gmainindicator"
    assert result["rows"][0]["report_date"] == "2026-03-31"
    assert result["rows"][0]["roe_avg"] == 1.23
    assert result["rows"][0]["basic_eps"] == 2.1


def test_sec_company_facts_uses_cik_mapping_and_standard_user_agent() -> None:
    session = FakeSession()
    session.responses[GlobalStockClient.SEC_TICKER_MAP_URL] = FakeResponse(
        {"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."}}
    )
    session.responses["https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"] = FakeResponse(
        {
            "cik": 320193,
            "entityName": "Apple Inc.",
            "facts": {"us-gaap": {"Revenues": {"units": {"USD": [{"fy": 2025, "val": 100}]}}}},
        }
    )

    result = GlobalStockClient(session=session, sec_user_agent="investment-agent test@example.com").get_sec_company_facts("AAPL")

    assert result["cik"] == "0000320193"
    assert result["entity_name"] == "Apple Inc."
    assert result["source"] == "sec_companyfacts"
    assert "Revenues" in result["facts"]["us-gaap"]
    assert session.calls[-1][2]["User-Agent"] == "investment-agent test@example.com"
