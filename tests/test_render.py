from datetime import date

from diarystats.archive import Archive, DayData
from diarystats.pipeline import render_day

DAY = date(2026, 10, 16)

EXPECTED_FULL = """\
==== Stats ====
  * **Sleep:** 7:12 h (score 78) · deep 1:21 · REM 1:40 · light 3:53 · awake 0:18 · 23:41–06:53
  * **HRV (overnight):** 52 ms · **Resting HR:** 51
  * **Body Battery:** max 84 / min 22 (+61 / −62)
  * **Stress avg:** 31 · **Steps:** 9,412
  * **RescueTime:** 8:05 h · pulse 71 · very productive 54 % · productive 12 % · distracting 9 %
  * **Top categories:** Software Development 4:10 · Communication and Scheduling 1:05 · Reference and Learning 0:50
  * //Raw data: lifelog/2026/10/16// · [[https://connect.garmin.com/modern/sleep/2026-10-16|Garmin]]
"""


def test_full_day(cfg, lifelog):
    archive = Archive(lifelog)
    assert render_day(cfg, archive, DAY, archive.load(DAY)) == EXPECTED_FULL


def test_sleep_not_synced(cfg, lifelog):
    archive = Archive(lifelog)
    data = archive.load(DAY)
    data.files["garmin"]["sleep"] = {"dailySleepDTO": {"sleepTimeSeconds": None}}
    data.files["garmin"]["hrv"] = None
    data.meta["garmin"]["complete"] = False
    text = render_day(cfg, archive, DAY, data)
    assert "**Sleep:** — ((Garmin data incomplete, maybe not synced yet))" in text
    # HRV falls back to nothing, resting HR still comes from the daily stats.
    assert "**HRV (overnight):** — · **Resting HR:** 51 ((" in text
    assert "**Steps:** 9,412\n" in text
    assert " 0:00" not in text


def test_garmin_auth_failure_keeps_rescuetime(cfg, lifelog):
    archive = Archive(lifelog)
    data = archive.load(DAY)
    data.files["garmin"] = {}
    data.meta["garmin"] = {"complete": False, "error": "auth failed"}
    text = render_day(cfg, archive, DAY, data)
    assert "**Garmin:** — ((Garmin fetch failed))" in text
    assert "Sleep" not in text
    assert "**RescueTime:** 8:05 h" in text


def test_nothing_archived(cfg, lifelog):
    text = render_day(cfg, Archive(lifelog), DAY, DayData())
    assert "**Garmin:** — ((no Garmin data))" in text
    assert "**RescueTime:** — ((no RescueTime data))" in text
    assert "Top categories" not in text


def test_metric_missing_in_complete_data(cfg, lifelog):
    archive = Archive(lifelog)
    data = archive.load(DAY)
    del data.files["garmin"]["stats"]["averageStressLevel"]
    text = render_day(cfg, archive, DAY, data)
    assert "**Stress avg:** — · **Steps:** 9,412 ((not recorded by Garmin))" in text


def test_negative_stress_is_missing(cfg, lifelog):
    archive = Archive(lifelog)
    data = archive.load(DAY)
    data.files["garmin"]["stats"]["averageStressLevel"] = -1
    assert "**Stress avg:** — ·" in render_day(cfg, archive, DAY, data)
