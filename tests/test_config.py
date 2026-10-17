import dataclasses
import os
from datetime import date

import pytest

from diarystats.config import ConfigError, load, load_env_file


def test_page_id(cfg):
    assert cfg.page_id(date(2026, 10, 7)) == "appreciation:2026:10:2026-10-07:stats"


def test_defaults_and_overrides(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text('timezone = "UTC"\n[diary]\nnamespace = "diary"\nstats_suffix = "_stats"\n')
    cfg = load(path)
    assert str(cfg.timezone) == "UTC"
    assert cfg.page_id(date(2026, 1, 2)) == "diary:2026:01:2026-01-02_stats"
    assert cfg.alert_backends == ("log",)


@pytest.mark.parametrize(
    "namestructure, name, expected",
    [
        # The same cases as in the yearbox plugin tests.
        ("separatedCompletely", "", "ns:2026:03:04"),
        ("YearMonthSeperatedNS", "", "ns:2026:03:2026-03-04"),
        ("YearMonthSeperatedNS", "day", "ns:2026:03:day-2026-03-04"),
        ("YearNS", "", "ns:2026:2026-03-04"),
        ("default", "day", "ns:2026-03:day-2026-03-04"),
    ],
)
def test_yearbox_strategies(cfg, namestructure, name, expected):
    cfg = dataclasses.replace(
        cfg, diary_namespace="ns", diary_namestructure=namestructure, diary_name=name
    )
    assert cfg.page_id(date(2026, 3, 4)) == expected + ":stats"


def test_unknown_namestructure(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text('[diary]\nnamestructure = "Weekly"\n')
    with pytest.raises(ConfigError, match="Weekly"):
        load(path)


def test_empty_namespace(cfg):
    cfg = dataclasses.replace(cfg, diary_namespace="")
    assert cfg.page_id(date(2026, 10, 7)) == "2026:10:2026-10-07:stats"


def test_missing_explicit_config(tmp_path):
    with pytest.raises(ConfigError):
        load(tmp_path / "nope.toml")


def test_unknown_sink(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text('[sink]\nkind = "wiki"\n')
    with pytest.raises(ConfigError):
        load(path)


def test_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DIARYSTATS_TEST_A", raising=False)
    monkeypatch.setenv("DIARYSTATS_TEST_B", "from-env")
    path = tmp_path / "env"
    path.write_text("# comment\nDIARYSTATS_TEST_A='x=1'\nDIARYSTATS_TEST_B=from-file\n")
    path.chmod(0o600)
    load_env_file(path)
    assert os.environ["DIARYSTATS_TEST_A"] == "x=1"
    assert os.environ["DIARYSTATS_TEST_B"] == "from-env"
    monkeypatch.delenv("DIARYSTATS_TEST_A")
