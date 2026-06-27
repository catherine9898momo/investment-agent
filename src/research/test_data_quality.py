from math import inf, nan

from src.research.data_quality import classify_history_points, finite_closes, is_finite_number


def test_is_finite_number_rejects_non_computable_values() -> None:
    assert is_finite_number(1)
    assert is_finite_number(1.5)
    assert not is_finite_number(nan)
    assert not is_finite_number(inf)
    assert not is_finite_number(None)
    assert not is_finite_number("123")


def test_finite_closes_keeps_only_numeric_finite_closes() -> None:
    bars = [
        {"close": 10.0},
        {"close": nan},
        {"close": inf},
        {"close": None},
        {"close": "11"},
        {"close": 12},
        "bad row",
    ]

    assert finite_closes(bars) == [10.0, 12.0]


def test_classify_history_points_distinguishes_range_trend_and_incomplete_window() -> None:
    assert classify_history_points([]).usable_for_range is False
    assert classify_history_points([10.0]).usable_for_range is False
    assert classify_history_points([10.0, 11.0]).usable_for_range is True
    assert classify_history_points([10.0, 11.0]).usable_for_trend is False
    assert classify_history_points([10.0, 11.0, 12.0]).usable_for_trend is True
    assert classify_history_points([10.0, 11.0, 12.0, 13.0]).window_complete is False
    assert classify_history_points([10.0, 11.0, 12.0, 13.0, 14.0]).window_complete is True
