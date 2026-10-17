import json
import subprocess
from datetime import date
from pathlib import Path

from diarystats.alert import Alerter
from diarystats.archive import Archive
from diarystats.fetch.garmin import GarminAuthError
from diarystats.pipeline import Fetcher, check_missing, day_range, process
from diarystats.sink import FileSink

FIXTURE_DAY = Path(__file__).parent / "fixtures/lifelog/2026/10/16"


def _fixture(name):
    return json.loads((FIXTURE_DAY / name).read_text())


GARMIN_FILES = {
    "sleep": _fixture("garmin_sleep.json"),
    "stats": _fixture("garmin_stats.json"),
    "body_battery": _fixture("garmin_body_battery.json"),
    "hrv": _fixture("garmin_hrv.json"),
}
RT_ROW = _fixture("rescuetime_daily_summary.json")


class FakeGarmin:
    def __init__(self, by_day=None, error=None):
        self.by_day = by_day or {}
        self.error = error
        self.calls = []

    def fetch(self, day):
        self.calls.append(day)
        if self.error:
            raise self.error
        return self.by_day.get(day, {"sleep": {}, "stats": {}, "body_battery": [], "hrv": None})


class FakeRescueTime:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def fetch_summary(self):
        self.calls += 1
        return self.rows


def _git_log(root):
    out = subprocess.run(
        ["git", "log", "--format=%s"], cwd=root, capture_output=True, text=True, check=True
    )
    return out.stdout.splitlines()


def _run(cfg, tmp_path, garmin, rescuetime, days):
    archive = Archive(tmp_path / "archive")
    alerter = Alerter()
    fetcher = Fetcher(garmin=garmin, rescuetime=rescuetime, alerter=alerter)
    sink = FileSink(cfg.sink_dir)
    ok = process(cfg, days, fetcher, archive, sink, alerter)
    return ok, archive, alerter


D1, D2, D3 = date(2026, 10, 14), date(2026, 10, 15), date(2026, 10, 16)


def test_run_archives_renders_and_commits(cfg, tmp_path):
    garmin = FakeGarmin({D3: GARMIN_FILES})
    rt = FakeRescueTime({D3: RT_ROW})
    ok, archive, alerter = _run(cfg, tmp_path, garmin, rt, [D3])
    assert ok
    assert alerter.sent == []
    assert archive.is_complete(D3, "garmin")
    assert archive.is_complete(D3, "rescuetime")
    assert (archive.day_dir(D3) / "garmin_sleep.json").exists()
    page = cfg.sink_dir / "appreciation/2026/10/2026-10-16/stats.txt"
    assert "7:12 h" in page.read_text()
    assert _git_log(archive.root) == ["lifelog: 2026-10-16"]

    # A second run with the same data changes nothing in the sink.
    mtime = page.stat().st_mtime_ns
    ok, _, _ = _run(cfg, tmp_path, garmin, rt, [D3])
    assert ok
    assert page.stat().st_mtime_ns == mtime


def test_rescuetime_is_fetched_once_per_run(cfg, tmp_path):
    rt = FakeRescueTime({D3: RT_ROW})
    _run(cfg, tmp_path, FakeGarmin(), rt, day_range(D1, D3))
    assert rt.calls == 1


def test_late_sync_completes_on_next_run(cfg, tmp_path):
    rt = FakeRescueTime({})
    ok, archive, _ = _run(cfg, tmp_path, FakeGarmin(), rt, [D3])
    assert ok
    assert not archive.is_complete(D3, "garmin")
    page = cfg.sink_dir / "appreciation/2026/10/2026-10-16/stats.txt"
    assert "maybe not synced yet" in page.read_text()

    _run(cfg, tmp_path, FakeGarmin({D3: GARMIN_FILES}), rt, [D3])
    assert archive.is_complete(D3, "garmin")
    assert "7:12 h" in page.read_text()


def test_garmin_auth_failure_alerts_once_and_keeps_rescuetime(cfg, tmp_path):
    garmin = FakeGarmin(error=GarminAuthError("token expired"))
    rows = {D: RT_ROW for D in (D1, D2, D3)}
    ok, archive, alerter = _run(cfg, tmp_path, garmin, FakeRescueTime(rows), [D1, D2, D3])
    assert not ok
    assert len(garmin.calls) == 1
    assert len(alerter.sent) == 1
    assert "login-garmin" in alerter.sent[0]
    for day in (D1, D2, D3):
        assert archive.is_complete(day, "rescuetime")
        assert not archive.is_complete(day, "garmin")
    page = cfg.sink_dir / "appreciation/2026/10/2026-10-16/stats.txt"
    text = page.read_text()
    assert "Garmin fetch failed" in text
    assert "**RescueTime:** 8:05 h" in text


def test_failed_fetch_keeps_old_data(cfg, tmp_path):
    _run(cfg, tmp_path, FakeGarmin({D3: GARMIN_FILES}), FakeRescueTime({}), [D3])
    garmin = FakeGarmin(error=GarminAuthError("token expired"))
    _, archive, _ = _run(cfg, tmp_path, garmin, FakeRescueTime({}), [D3])
    assert archive.is_complete(D3, "garmin")
    assert archive.load(D3).meta["garmin"]["error"].startswith("auth failed")


def test_check_missing(tmp_path):
    archive = Archive(tmp_path)
    alerter = Alerter()
    today = date(2026, 10, 17)
    check_missing(archive, alerter, today)
    assert len(alerter.sent) == 2

    alerter = Alerter()
    from diarystats.archive import SourceResult

    archive.apply(D2, "garmin", SourceResult({"stats": {}}, complete=True))
    check_missing(archive, alerter, today)
    assert len(alerter.sent) == 1
    assert "rescuetime" in alerter.sent[0]


def test_archive_days(cfg, tmp_path):
    _run(cfg, tmp_path, FakeGarmin({D3: GARMIN_FILES}), FakeRescueTime({D3: RT_ROW}), [D1, D3])
    assert list(Archive(tmp_path / "archive").days()) == [D1, D3]
