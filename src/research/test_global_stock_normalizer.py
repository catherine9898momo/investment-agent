from src.research.fact_verifier import build_verified_fact_table
from src.research.normalizers import normalize_global_stock_snapshot


def test_global_stock_snapshot_normalizes_first_phase_data_to_traceable_facts() -> None:
    normalized = normalize_global_stock_snapshot(
        {
            "fundamentals": {
                "symbol": "AAPL",
                "source": "eastmoney_gmainindicator",
                "rows": [{"report_date": "2026-03-31", "roe_avg": 1.2, "basic_eps": 2.1}],
            },
            "sec_company_facts": {
                "symbol": "AAPL",
                "source": "sec_companyfacts",
                "cik": "0000320193",
                "entity_name": "Apple Inc.",
                "facts": {"us-gaap": {"Revenues": {}}},
            },
            "search": [{"symbol": "AAPL", "name": "Apple Inc.", "market": "US", "secid": "105.AAPL"}],
            "market_list": [{"symbol": "AAPL", "name": "Apple Inc.", "latest_price": 201.0, "change_pct": 1.2}],
        },
        "AAPL",
    )

    metrics = {fact.metric for fact in normalized.facts}

    assert metrics == {"fundamentals", "sec_company_facts", "stock_search", "market_list"}
    assert all(fact.source_ids for fact in normalized.facts)
    assert {source.reliability for source in normalized.sources} == {"high", "medium"}

    verified, _ = build_verified_fact_table(normalized.facts, None)
    assert {"fundamentals", "sec_filings", "market_universe"}.issubset({fact.fact_type for fact in verified})
