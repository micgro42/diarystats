import json
from datetime import date

import pytest

from diarystats.archive import Archive, SourceResult
from diarystats.importer import ImportError_, import_rescuetime
from diarystats.metrics import rescuetime_metrics

HEADERS = ["Date", "Time Spent (seconds)", "Number of People"]


def _export(tmp_path, kind, last_header, rows):
    path = tmp_path / f"rt-interval-{kind}-2026-10-17.json"
    path.write_text(json.dumps({"row_headers": [*HEADERS, last_header], "rows": rows}))
    return path


def test_import_splits_by_day_and_computes_metrics(tmp_path):
    productivity = _export(
        tmp_path,
        "productivity",
        "Productivity",
        [
            ["2026-08-01T00:00:00", 3600, 1, 2],
            ["2026-08-01T00:00:00", 1800, 1, 0],
            ["2026-08-01T00:00:00", 1800, 1, -2],
            ["2026-08-02T00:00:00", 600, 1, 1],
        ],
    )
    overview = _export(
        tmp_path,
        "overview",
        "Category",
        [
            ["2026-08-01T00:00:00", 4000, 1, "Software Development"],
            ["2026-08-01T00:00:00", 2000, 1, "Uncategorized"],
            ["2026-08-01T00:00:00", 1200, 1, "News & Opinion"],
        ],
    )
    archive = Archive(tmp_path / "lifelog")
    days = import_rescuetime(archive, [productivity, overview])
    assert days == [date(2026, 8, 1), date(2026, 8, 2)]
    assert archive.is_complete(date(2026, 8, 1), "rescuetime")

    m = rescuetime_metrics(archive.load(date(2026, 8, 1)).files["rescuetime"])
    assert m.total_hours == 2
    # (100 * 3600 + 50 * 1800 + 0 * 1800) / 7200 = 62.5, rounded down.
    assert m.pulse == 62
    assert (m.productive_pct, m.neutral_pct, m.distracting_pct) == (50, 25, 25)
    assert [name for name, _ in m.top_categories] == ["Software Development", "News & Opinion"]


def test_feed_wins_over_import(tmp_path):
    archive = Archive(tmp_path / "lifelog")
    day = date(2026, 8, 1)
    feed = {"date": "2026-08-01", "total_hours": 5.0, "productivity_pulse": 80}
    archive.apply(day, "rescuetime", SourceResult({"daily_summary": feed}, complete=True))
    path = _export(tmp_path, "productivity", "Productivity", [["2026-08-01T00:00:00", 60, 1, 0]])
    import_rescuetime(archive, [path])
    files = archive.load(day).files["rescuetime"]
    assert set(files) == {"daily_summary", "interval_productivity"}
    assert rescuetime_metrics(files).pulse == 80


def test_rate_limit_message_fails(tmp_path):
    path = tmp_path / "rt-interval-overview-x.json"
    path.write_text('{"message": "Please wait 5 minutes."}')
    with pytest.raises(ImportError_, match="Please wait 5 minutes"):
        import_rescuetime(Archive(tmp_path / "lifelog"), [path])


def test_bad_file_name(tmp_path):
    path = tmp_path / "export.json"
    path.write_text("{}")
    with pytest.raises(ImportError_, match="rt-interval"):
        import_rescuetime(Archive(tmp_path / "lifelog"), [path])
