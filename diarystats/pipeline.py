"""Fetch, archive and render a range of days.

Each source fails on its own. A Garmin failure does not stop RescueTime,
and the reverse.
"""

import logging
import subprocess
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable, Protocol

from .alert import Alerter
from .archive import Archive, DayData, SourceResult
from .config import Config
from .fetch.garmin import GarminAuthError, GarminFetchError
from .fetch.rescuetime import RescueTimeError
from .metrics import garmin_metrics, rescuetime_metrics
from .render import render
from .sink import Sink

log = logging.getLogger(__name__)

# Alert if this many recent days in a row have no complete data.
MISSING_STREAK = 3


class GarminLike(Protocol):
    def fetch(self, day: date) -> dict[str, Any]: ...


class RescueTimeLike(Protocol):
    def fetch_summary(self) -> dict[date, dict[str, Any]]: ...


@dataclass
class Fetcher:
    """Fetch both sources for single days. Remember failures within one run."""

    garmin: GarminLike | None
    rescuetime: RescueTimeLike | None
    alerter: Alerter
    garmin_info: dict[str, Any] = field(default_factory=dict)
    failed: bool = False
    _garmin_dead: str | None = None
    _garmin_alerted: bool = False
    _rt_rows: dict[date, dict[str, Any]] | None = None
    _rt_error: str | None = None

    def fetch_day(self, day: date) -> dict[str, SourceResult]:
        return {"garmin": self._garmin(day), "rescuetime": self._rescuetime(day)}

    def _garmin(self, day: date) -> SourceResult:
        if self.garmin is None:
            return SourceResult(None)
        if self._garmin_dead:
            return SourceResult(None, error=self._garmin_dead)
        try:
            files = self.garmin.fetch(day)
        except GarminAuthError as e:
            self.failed = True
            self._garmin_dead = f"auth failed: {e}"
            self.alerter.alert(f"diarystats: Garmin auth failed. Run login-garmin. ({e})")
            return SourceResult(None, error=self._garmin_dead)
        except GarminFetchError as e:
            self.failed = True
            log.error("garmin %s: %s", day, e)
            if not self._garmin_alerted:
                self._garmin_alerted = True
                self.alerter.alert(f"diarystats: Garmin fetch failed ({e})")
            return SourceResult(None, error=str(e))
        complete = garmin_metrics(files).complete
        if not complete:
            log.info("garmin %s: incomplete data", day)
        return SourceResult(files, complete=complete, info=self.garmin_info)

    def _rescuetime(self, day: date) -> SourceResult:
        if self.rescuetime is None:
            return SourceResult(None)
        if self._rt_rows is None and self._rt_error is None:
            try:
                self._rt_rows = self.rescuetime.fetch_summary()
            except RescueTimeError as e:
                self.failed = True
                self._rt_error = str(e)
                self.alerter.alert(f"diarystats: RescueTime fetch failed ({e})")
        if self._rt_error:
            return SourceResult(None, error=self._rt_error)
        row = self._rt_rows.get(day)
        if row is None:
            log.info("rescuetime %s: not in daily_summary_feed", day)
            return SourceResult(None)
        files = {"daily_summary": row}
        return SourceResult(files, complete=rescuetime_metrics(files).complete)


def render_day(cfg: Config, archive: Archive, day: date, data: DayData) -> str:
    return render(
        day,
        data,
        tz=cfg.timezone,
        raw_path=archive.rel_day_dir(day),
        garmin_link=cfg.garmin_link,
        rescuetime_link=cfg.rescuetime_link,
    )


def write_rendered(cfg: Config, archive: Archive, sink: Sink, day: date) -> bool:
    text = render_day(cfg, archive, day, archive.load(day))
    return sink.write(cfg.page_id(day), text)


def process(
    cfg: Config,
    days: list[date],
    fetcher: Fetcher,
    archive: Archive,
    sink: Sink,
    alerter: Alerter,
    throttle: float = 0,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Fetch, archive and render the days. Return False if anything failed."""
    ok = True
    for i, day in enumerate(days):
        if i and throttle:
            sleep(throttle)
        for source, result in fetcher.fetch_day(day).items():
            archive.apply(day, source, result)
        try:
            write_rendered(cfg, archive, sink, day)
        except OSError as e:
            ok = False
            alerter.alert(f"diarystats: cannot write stats page for {day} ({e})")

    if days:
        label = days[0].isoformat() if len(days) == 1 else f"{days[0]}..{days[-1]}"
        try:
            archive.commit(f"lifelog: {label}")
        except (OSError, subprocess.CalledProcessError) as e:
            ok = False
            alerter.alert(f"diarystats: archive commit failed ({e})")

    return ok and not fetcher.failed


def check_missing(archive: Archive, alerter: Alerter, today: date) -> None:
    """Alert if a source has no complete data for the last MISSING_STREAK days."""
    recent = [today - timedelta(days=n) for n in range(1, MISSING_STREAK + 1)]
    for source in ("garmin", "rescuetime"):
        if not any(archive.is_complete(day, source) for day in recent):
            alerter.alert(
                f"diarystats: no complete {source} data for {MISSING_STREAK} days"
                f" ({recent[-1]}..{recent[0]})"
            )


def day_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=n) for n in range((end - start).days + 1)]
