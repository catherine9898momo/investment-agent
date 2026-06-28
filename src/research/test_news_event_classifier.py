from src.research.models import Fact
from src.research.news_event_classifier import classify_news_events


def _news_fact(titles: list[str]) -> Fact:
    return Fact(
        id="fact_news",
        text="Recent news snapshot.",
        source_ids=["src_news"],
        observed_at="2026-06-28",
        metric="news_tone",
        value={"items": [{"title": title} for title in titles]},
        symbol="MU",
    )


def test_classifies_micron_earnings_and_ai_trade_news_events() -> None:
    events = classify_news_events([
        _news_fact([
            "Micron Earnings Beat Estimates but Outlook Raises Questions",
            "AI Memory Demand Linked to Nvidia Keeps Investors Focused",
        ])
    ])

    assert [event.event_type for event in events] == ["earnings_or_guidance", "ai_trade"]
    assert events[0].supporting_fact_ids == ["fact_news"]
    assert events[0].source_titles == ["Micron Earnings Beat Estimates but Outlook Raises Questions"]


def test_classifies_sector_peer_and_analyst_events_with_priority() -> None:
    events = classify_news_events([
        _news_fact([
            "Micron Stock Falls After Memory Rivals SK Hynix and Samsung Sink",
            "Analyst Downgrades Micron and Cuts Price Target",
        ])
    ])

    assert [event.event_type for event in events] == ["sector_peer", "analyst_action"]
    assert events[0].label == "板块/同行同步信号"


def test_unknown_news_remains_conservative() -> None:
    events = classify_news_events([_news_fact(["Micron Announces Community Event"])])

    assert events[0].event_type == "unknown"
    assert events[0].confidence == "low"

