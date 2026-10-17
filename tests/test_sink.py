import subprocess

import pytest

from diarystats.sink import DwpageSink, FileSink


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



class FakeRun:
    def __init__(self, returncode=0, stderr=""):
        self.calls = []
        self.returncode = returncode
        self.stderr = stderr

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs["input"]))
        return subprocess.CompletedProcess(args, self.returncode, "", self.stderr)


def test_dwpage_saves_new_and_changed_pages(tmp_path):
    run = FakeRun()
    sink = DwpageSink(tmp_path, ("sudo", "wrapper"), run=run)
    page = "appreciation:2026:10:2026-10-16:stats"
    assert sink.write(page, "new\n") is True
    assert run.calls == [(["sudo", "wrapper", page], "new\n")]


def test_dwpage_skips_unchanged_page(tmp_path):
    page = "appreciation:2026:10:2026-10-16:stats"
    path = tmp_path / "appreciation/2026/10/2026-10-16/stats.txt"
    path.parent.mkdir(parents=True)
    path.write_text("same\n")
    run = FakeRun()
    assert DwpageSink(tmp_path, ("wrapper",), run=run).write(page, "same\n") is False
    assert run.calls == []


def test_dwpage_failure_raises_oserror(tmp_path):
    run = FakeRun(returncode=1, stderr="Page is already locked by another user")
    with pytest.raises(OSError, match="locked"):
        DwpageSink(tmp_path, ("wrapper",), run=run).write("a:stats", "x\n")
