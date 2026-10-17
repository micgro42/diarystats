"""Render the archived data of one day as a DokuWiki snippet."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from .archive import DayData
from .metrics import GarminMetrics, RescueTimeMetrics, garmin_metrics, rescuetime_metrics

MISSING = "—"


def _dur(seconds: float | None) -> str:
    """Format seconds as H:MM."""
    if seconds is None:
        return MISSING
    minutes = round(seconds / 60)
    return f"{minutes // 60}:{minutes % 60:02d}"


def _hours(hours: float | None) -> str:
    return MISSING if hours is None else _dur(hours * 3600)


def _num(value: float | None, fmt: str = "{:,.0f}") -> str:
    return MISSING if value is None else fmt.format(value)


def _pct(value: float | None) -> str:
    return MISSING if value is None else f"{value:.0f} %"


def _label(key: str) -> str:
    """Make a Garmin qualifier key readable: "NOT_ENOUGH_DATA" → "not enough data"."""
    return key.replace("_", " ").lower()


def _clock(moment: datetime | None, tz: ZoneInfo) -> str:
    return MISSING if moment is None else f"{moment.astimezone(tz):%H:%M}"


def _reason(label: str, meta: dict, has_data: bool, complete: bool) -> str:
    if not has_data:
        return f"{label} fetch failed" if meta.get("error") else f"no {label} data"
    if not complete:
        return f"{label} data incomplete, maybe not synced yet"
    return f"not recorded by {label}"


def _line(label: str, parts: list[str], note: str) -> str:
    """Return a list item. Add a footnote if a part is missing."""
    text = " · ".join(parts)
    if MISSING in text:
        text += f" (({note}))"
    return f"  * **{label}:** {text}"


def _garmin_lines(g: GarminMetrics, note: str, tz: ZoneInfo) -> list[str]:
    if g.has_sleep:
        quality = f", {_label(g.sleep_quality)}" if g.sleep_quality else ""
        score = f" (score {_num(g.sleep_score)}{quality})"
        sleep = [
            f"{_dur(g.sleep_seconds)} h{score}",
            f"deep {_dur(g.deep_seconds)}",
            f"REM {_dur(g.rem_seconds)}",
            f"light {_dur(g.light_seconds)}",
            f"awake {_dur(g.awake_seconds)}",
            f"{_clock(g.sleep_start, tz)}–{_clock(g.sleep_end, tz)}",
        ]
    else:
        sleep = [MISSING]

    if g.hrv_overnight is None:
        hrv = MISSING
    else:
        status = f" ({_label(g.hrv_status)})" if g.hrv_status else ""
        hrv = f"{_num(g.hrv_overnight)} ms{status}"
    if g.bb_max is None and g.bb_min is None:
        battery = MISSING
    else:
        battery = (
            f"max {_num(g.bb_max)} / min {_num(g.bb_min)}"
            f" (+{_num(g.bb_charged)} / −{_num(g.bb_drained)})"
        )

    return [
        _line("Sleep", sleep, note),
        _line("HRV (overnight)", [hrv, f"**Resting HR:** {_num(g.resting_hr)}"], note),
        _line("Body Battery", [battery], note),
        _line("Stress avg", [_num(g.stress_avg), f"**Steps:** {_num(g.steps)}"], note),
    ]


def _rescuetime_lines(r: RescueTimeMetrics, note: str) -> list[str]:
    if r.total_hours is None:
        return [_line("RescueTime", [MISSING], note)]
    lines = [
        _line(
            "RescueTime",
            [
                f"{_hours(r.total_hours)} h",
                f"pulse {_num(r.pulse)}",
                f"productive {_pct(r.productive_pct)}",
                f"neutral {_pct(r.neutral_pct)}",
                f"distracting {_pct(r.distracting_pct)}",
            ],
            note,
        )
    ]
    if r.top_categories:
        cats = [f"{name} {_hours(hours)}" for name, hours in r.top_categories]
        lines.append(_line("Top categories", cats, note))
    return lines


def _link(template: str, label: str, day: date) -> str | None:
    if not template:
        return None
    return f"[[{template.format(date=day.isoformat())}|{label}]]"


def render(
    day: date,
    data: DayData,
    *,
    tz: ZoneInfo,
    raw_path: str,
    garmin_link: str = "",
    rescuetime_link: str = "",
) -> str:
    garmin_files = data.files.get("garmin", {})
    rt_files = data.files.get("rescuetime", {})
    g = garmin_metrics(garmin_files)
    r = rescuetime_metrics(rt_files)

    g_note = _reason("Garmin", data.meta.get("garmin", {}), bool(garmin_files), g.complete)
    r_note = _reason("RescueTime", data.meta.get("rescuetime", {}), bool(rt_files), r.complete)

    footer = [f"//Raw data: {raw_path}//"]
    footer += [
        link
        for link in (
            _link(garmin_link, "Garmin", day),
            _link(rescuetime_link, "RescueTime", day),
        )
        if link
    ]

    lines = ["==== Stats ===="]
    if garmin_files:
        lines += _garmin_lines(g, g_note, tz)
    else:
        lines.append(_line("Garmin", [MISSING], g_note))
    lines += _rescuetime_lines(r, r_note)
    lines.append("  * " + " · ".join(footer))
    return "\n".join(lines) + "\n"
