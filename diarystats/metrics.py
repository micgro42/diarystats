"""Extract display metrics from raw API responses.

This module holds all knowledge about the field names in the API responses.
If Garmin or RescueTime change their responses, change this module.

The Garmin field names are not verified against real responses yet.
Verify them with real fixtures before you trust the output.
"""

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
    deep_seconds: int | None = None
    light_seconds: int | None = None
    rem_seconds: int | None = None
    awake_seconds: int | None = None
    sleep_start: datetime | None = None
    sleep_end: datetime | None = None
    hrv_overnight: int | None = None
    resting_hr: int | None = None
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
        resting_hr=_first(
            _get(stats, "restingHeartRate"),
            _get(files, "sleep", "restingHeartRate"),
        ),
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


@dataclass(frozen=True)
class RescueTimeMetrics:
    total_hours: float | None = None
    pulse: int | None = None
    very_productive_pct: float | None = None
    productive_pct: float | None = None
    distracting_pct: float | None = None
    top_categories: tuple[tuple[str, float], ...] = ()

    @property
    def complete(self) -> bool:
        return self.total_hours is not None


def _category_label(key: str) -> str:
    words = key.split("_")
    return " ".join(w if w == "and" else w.capitalize() for w in words)


def rescuetime_metrics(files: dict[str, Any], top: int = 3) -> RescueTimeMetrics:
    """Extract metrics from one row of the RescueTime daily_summary_feed."""
    row = files.get("daily_summary")
    if not isinstance(row, dict):
        return RescueTimeMetrics()

    categories = []
    for key, value in row.items():
        if not key.endswith("_hours"):
            continue
        name = key[: -len("_hours")]
        if name in _NOT_CATEGORIES or not isinstance(value, (int, float)) or value <= 0:
            continue
        categories.append((_category_label(name), float(value)))
    categories.sort(key=lambda c: c[1], reverse=True)

    return RescueTimeMetrics(
        total_hours=row.get("total_hours"),
        pulse=row.get("productivity_pulse"),
        very_productive_pct=row.get("very_productive_percentage"),
        productive_pct=row.get("productive_percentage"),
        distracting_pct=row.get("all_distracting_percentage"),
        top_categories=tuple(categories[:top]),
    )
