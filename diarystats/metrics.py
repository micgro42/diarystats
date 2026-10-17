"""Extract display metrics from raw API responses.

This module holds all knowledge about the field names in the API responses.
If Garmin or RescueTime change their responses, change this module.

The field names were checked against live responses on 2026-10-17.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _get(obj: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _first(*values: Any) -> Any:
    return next((v for v in values if v is not None), None)


def _timestamp(ms: Any) -> datetime | None:
    if not isinstance(ms, (int, float)):
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


@dataclass(frozen=True)
class GarminMetrics:
    sleep_seconds: int | None = None
    sleep_score: int | None = None
    sleep_quality: str | None = None
    deep_seconds: int | None = None
    light_seconds: int | None = None
    rem_seconds: int | None = None
    awake_seconds: int | None = None
    sleep_start: datetime | None = None
    sleep_end: datetime | None = None
    hrv_overnight: int | None = None
    hrv_status: str | None = None
    resting_hr: int | None = None
    sleep_hr_avg: int | None = None
    bb_max: int | None = None
    bb_min: int | None = None
    bb_charged: int | None = None
    bb_drained: int | None = None
    stress_avg: int | None = None
    steps: int | None = None

    @property
    def has_sleep(self) -> bool:
        return self.sleep_seconds is not None

    @property
    def has_daily(self) -> bool:
        return self.steps is not None

    @property
    def complete(self) -> bool:
        return self.has_sleep and self.has_daily


def garmin_metrics(files: dict[str, Any]) -> GarminMetrics:
    """Extract metrics from the files of fetch.garmin.ENDPOINTS."""
    sleep = _get(files, "sleep", "dailySleepDTO")
    stats = files.get("stats")
    hrv = files.get("hrv")

    sleep_seconds = _get(sleep, "sleepTimeSeconds")
    # Garmin can send a sleep record with zero sleep before the watch syncs.
    if not sleep_seconds:
        sleep_seconds = None

    # Garmin sends -1 or negative values for "no stress data".
    stress = _get(stats, "averageStressLevel")
    if isinstance(stress, (int, float)) and stress < 0:
        stress = None

    return GarminMetrics(
        sleep_seconds=sleep_seconds,
        sleep_score=_get(sleep, "sleepScores", "overall", "value"),
        sleep_quality=_get(sleep, "sleepScores", "overall", "qualifierKey"),
        deep_seconds=_get(sleep, "deepSleepSeconds"),
        light_seconds=_get(sleep, "lightSleepSeconds"),
        rem_seconds=_get(sleep, "remSleepSeconds"),
        awake_seconds=_get(sleep, "awakeSleepSeconds"),
        sleep_start=_timestamp(_get(sleep, "sleepStartTimestampGMT")),
        sleep_end=_timestamp(_get(sleep, "sleepEndTimestampGMT")),
        hrv_overnight=_first(
            _get(hrv, "hrvSummary", "lastNightAvg"),
            _get(files, "sleep", "avgOvernightHrv"),
        ),
        hrv_status=_first(
            _get(hrv, "hrvSummary", "status"),
            _get(files, "sleep", "hrvStatus"),
        ),
        resting_hr=_first(
            _get(stats, "restingHeartRate"),
            _get(files, "sleep", "restingHeartRate"),
        ),
        sleep_hr_avg=_get(sleep, "avgHeartRate"),
        bb_max=_get(stats, "bodyBatteryHighestValue"),
        bb_min=_get(stats, "bodyBatteryLowestValue"),
        bb_charged=_get(stats, "bodyBatteryChargedValue"),
        bb_drained=_get(stats, "bodyBatteryDrainedValue"),
        stress_avg=stress,
        steps=_get(stats, "totalSteps"),
    )


# Keys of a daily_summary_feed row that end in "_hours" but are not categories.
_NOT_CATEGORIES = {
    "total",
    "all_productive",
    "all_distracting",
    "very_productive",
    "productive",
    "neutral",
    "distracting",
    "very_distracting",
    "uncategorized",
}

# Weights of the RescueTime productivity levels for the productivity pulse.
# Checked against daily_summary_feed: the pulse is the weighted mean, rounded down.
_PULSE_WEIGHTS = {2: 100, 1: 75, 0: 50, -1: 25, -2: 0}

# Overview category names that the feed does not count as categories either.
_NOT_CATEGORY_NAMES = {"Uncategorized"}


@dataclass(frozen=True)
class RescueTimeMetrics:
    total_hours: float | None = None
    pulse: int | None = None
    productive_pct: float | None = None
    neutral_pct: float | None = None
    distracting_pct: float | None = None
    top_categories: tuple[tuple[str, float], ...] = ()

    @property
    def complete(self) -> bool:
        return self.total_hours is not None


# Feed keys of the RescueTime top-level categories, mapped to the names that
# /anapi/data exports use. Use the same names for both sources.
_CATEGORY_NAMES = {
    "business": "Business",
    "communication_and_scheduling": "Communication & Scheduling",
    "design_and_composition": "Design & Composition",
    "entertainment": "Entertainment",
    "news": "News & Opinion",
    "reference_and_learning": "Reference & Learning",
    "shopping": "Shopping",
    "social_networking": "Social Networking",
    "software_development": "Software Development",
    "utilities": "Utilities",
}


def _category_label(key: str) -> str:
    if key in _CATEGORY_NAMES:
        return _CATEGORY_NAMES[key]
    words = key.split("_")
    return " ".join(w if w == "and" else w.capitalize() for w in words)


def _feed_categories(row: dict[str, Any]) -> list[tuple[str, float]]:
    categories = []
    for key, value in row.items():
        if not key.endswith("_hours"):
            continue
        name = key[: -len("_hours")]
        if name in _NOT_CATEGORIES or not isinstance(value, (int, float)) or value <= 0:
            continue
        categories.append((_category_label(name), float(value)))
    return categories


def _interval_rows(export: Any) -> list[tuple[float, Any]]:
    """Return (seconds, kind value) for each row of an /anapi/data interval export."""
    if not isinstance(export, dict):
        return []
    headers = export.get("row_headers", [])
    try:
        time_col = headers.index("Time Spent (seconds)")
    except ValueError:
        return []
    kind_col = len(headers) - 1
    return [(row[time_col], row[kind_col]) for row in export.get("rows", [])]


def _sum_by_kind(export: Any) -> dict[Any, float]:
    """Return the total seconds for each value of the kind column."""
    sums: dict[Any, float] = {}
    for seconds, kind in _interval_rows(export):
        sums[kind] = sums.get(kind, 0) + seconds
    return sums


def _from_feed(row: dict[str, Any]) -> RescueTimeMetrics:
    return RescueTimeMetrics(
        total_hours=row.get("total_hours"),
        pulse=row.get("productivity_pulse"),
        productive_pct=row.get("all_productive_percentage"),
        neutral_pct=row.get("neutral_percentage"),
        distracting_pct=row.get("all_distracting_percentage"),
    )


def _from_interval(export: Any) -> RescueTimeMetrics:
    by_level = _sum_by_kind(export)
    total = sum(by_level.values())
    if not total:
        return RescueTimeMetrics()

    def pct(*levels: int) -> float:
        return 100 * sum(by_level.get(level, 0) for level in levels) / total

    pulse = sum(_PULSE_WEIGHTS.get(level, 0) * s for level, s in by_level.items()) / total
    return RescueTimeMetrics(
        total_hours=total / 3600,
        pulse=math.floor(pulse),
        productive_pct=pct(2, 1),
        neutral_pct=pct(0),
        distracting_pct=pct(-1, -2),
    )


def rescuetime_metrics(files: dict[str, Any], top: int = 3) -> RescueTimeMetrics:
    """Extract metrics from the RescueTime files of one day.

    Use the daily_summary_feed row if there is one. Else use the imported
    /anapi/data exports (interval_productivity, interval_overview).
    """
    row = files.get("daily_summary")
    if isinstance(row, dict):
        metrics = _from_feed(row)
        categories = _feed_categories(row)
    else:
        metrics = _from_interval(files.get("interval_productivity"))
        categories = [
            (str(name), seconds / 3600)
            for name, seconds in _sum_by_kind(files.get("interval_overview")).items()
            if seconds > 0 and name not in _NOT_CATEGORY_NAMES
        ]
    categories.sort(key=lambda c: c[1], reverse=True)
    return RescueTimeMetrics(
        total_hours=metrics.total_hours,
        pulse=metrics.pulse,
        productive_pct=metrics.productive_pct,
        neutral_pct=metrics.neutral_pct,
        distracting_pct=metrics.distracting_pct,
        top_categories=tuple(categories[:top]),
    )

