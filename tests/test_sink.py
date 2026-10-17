from diarystats.sink import FileSink


def test_unchanged_content_is_not_written(tmp_path):
    sink = FileSink(tmp_path)
    page = "appreciation:2026:10:2026-10-16:stats"
    assert sink.write(page, "a\n") is True
    path = tmp_path / "appreciation/2026/10/2026-10-16/stats.txt"
    assert path.read_text() == "a\n"
    mtime = path.stat().st_mtime_ns
    assert sink.write(page, "a\n") is False
    assert path.stat().st_mtime_ns == mtime
    assert sink.write(page, "b\n") is True
