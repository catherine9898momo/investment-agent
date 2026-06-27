"""Shared data quality helpers for research normalization and rendering."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any


DEFAULT_HISTORY_POINT_COUNT = 5
MIN_CLOSES_FOR_RANGE = 2
MIN_CLOSES_FOR_TREND = 3


@dataclass(frozen=True)
class HistoryPointClassification:
    valid_close_count: int
    requested_close_count: int = DEFAULT_HISTORY_POINT_COUNT
    usable_for_range: bool = False
    usable_for_trend: bool = False
    window_complete: bool = False


def is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(float(value))


def finite_closes(bars: list[Any]) -> list[float]:
    closes: list[float] = []
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        close = bar.get("close")
        if is_finite_number(close):
            closes.append(float(close))
    return closes


def classify_history_points(closes: list[float], requested_count: int = DEFAULT_HISTORY_POINT_COUNT) -> HistoryPointClassification:
    count = len(closes)
    return HistoryPointClassification(
        valid_close_count=count,
        requested_close_count=requested_count,
        usable_for_range=count >= MIN_CLOSES_FOR_RANGE,
        usable_for_trend=count >= MIN_CLOSES_FOR_TREND,
        window_complete=count >= requested_count,
    )
