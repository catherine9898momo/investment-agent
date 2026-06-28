from src.research.live_enhanced_evidence import (
    extract_analyst_actions,
    extract_earnings_guidance,
    extract_macro_context,
)


def test_extract_analyst_actions_filters_live_news_titles_without_fixture_payload() -> None:
    news = {
        "items": [
            {"title": "Micron price target hiked by analysts after AI demand update", "source": "Investing.com"},
            {"title": "Micron shares fall with memory rivals", "source": "Barron's"},
        ]
    }

    payload = extract_analyst_actions(news)

    assert payload["items"]
    assert payload["items"][0]["source"] == "Investing.com"
    assert "Fixture" not in payload["items"][0]["detail"]
    assert "price target" in payload["items"][0]["detail"].lower()


def test_extract_earnings_guidance_filters_live_news_titles() -> None:
    news = {
        "items": [
            {"title": "Micron earnings outlook raises margin questions", "source": "Morningstar"},
            {"title": "Micron shares fall with memory rivals", "source": "Barron's"},
        ]
    }

    payload = extract_earnings_guidance(news)

    assert payload["items"]
    assert payload["items"][0]["source"] == "Morningstar"
    assert "earnings" in payload["items"][0]["detail"].lower()


def test_extract_macro_context_uses_live_history_symbols() -> None:
    sector_history = {
        "period": "5d",
        "items": [
            {"symbol": "QQQ", "label": "Nasdaq 100 ETF", "status": "ok", "change_pct": -2.0},
            {"symbol": "SMH", "label": "Semiconductor ETF", "status": "ok", "change_pct": -3.0},
        ],
    }

    payload = extract_macro_context(sector_history)

    assert payload["items"] == [
        {"symbol": "QQQ", "label": "Nasdaq 100 ETF", "change_pct": -2.0, "detail": "QQQ 5d change -2.00%"},
        {"symbol": "SMH", "label": "Semiconductor ETF", "change_pct": -3.0, "detail": "SMH 5d change -3.00%"},
    ]
