from datetime import date

from src.research.time_window import resolve_time_window


def test_resolve_recent_drop_window() -> None:
    window = resolve_time_window("美光最近为什么会大跌？", today=date(2026, 6, 7))

    assert window.label == "最近 5 个交易日左右"
    assert window.start_date == "2026-05-31"
    assert window.end_date == "2026-06-07"
    assert window.confidence == "medium"
