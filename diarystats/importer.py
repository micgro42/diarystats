"""Import RescueTime /anapi/data interval exports into the archive.

The free plan keeps only about 3 months of history, and daily_summary_feed
covers only about 14 days. Exports of /anapi/data with perspective=interval
and resolution_time=day keep the older days.

The file name gives the export kind: rt-interval-<kind>-<anything>.json
"""

import json
import logging
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from .archive import Archive, SourceResult
from .metrics import rescuetime_metrics

log = logging.getLogger(__name__)

FILE_PATTERN = re.compile(r"^rt-interval-([a-z]+)-")


class ImportError_(Exception):
    pass


def _load(path: Path) -> tuple[str, dict[str, Any]]:
    match = FILE_PATTERN.match(path.name)
    if not match:
        raise ImportError_(f"{path.name}: name must start with rt-interval-<kind>-")
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or "rows" not in data:
        message = data.get("message") if isinstance(data, dict) else None
        raise ImportError_(f"{path.name}: no rows ({message or 'unexpected format'})")
    return match.group(1), data


def split_by_day(paths: list[Path]) -> dict[date, dict[str, Any]]:
    """Return {day: {"interval_<kind>": export with only the rows of that day}}."""
    days: dict[date, dict[str, Any]] = defaultdict(dict)
    for path in paths:
        kind, data = _load(path)
        headers = data["row_headers"]
        rows_by_day: dict[date, list] = defaultdict(list)
        for row in data["rows"]:
            rows_by_day[date.fromisoformat(str(row[0])[:10])].append(row)
        for day, rows in rows_by_day.items():
            days[day][f"interval_{kind}"] = {"row_headers": headers, "rows": rows}
        log.info("import: %s, %d rows, %d days", path.name, len(data["rows"]), len(rows_by_day))
    return dict(days)


def import_rescuetime(archive: Archive, paths: list[Path]) -> list[date]:
    """Write the exports to the archive. Return the imported days in order.

    The import adds files. It does not delete a daily_summary from the feed,
    and the renderer prefers the feed.
    """
    days = split_by_day(paths)
    for day in sorted(days):
        files = days[day]
        existing = archive.load(day).files.get("rescuetime", {})
        complete = rescuetime_metrics({**existing, **files}).complete
        names = sorted(p.name for p in paths)
        archive.apply(
            day,
            "rescuetime",
            SourceResult(files, complete=complete, info={"imported_from": names}),
        )
    return sorted(days)
