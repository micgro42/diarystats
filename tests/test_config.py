import dataclasses
from datetime import date

import pytest

from diarystats.config import ConfigError, load, load_env_file, php_date


def test_page_id(cfg):
    assert cfg.page_id(date(2026, 10, 7)) == "appreciation:2026:10:2026-10-07:stats"


def test_defaults_and_overrides(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text(
        'timezone = "UTC"\n[diary]\nnamespace = "diary"\nformat = "Y-n-j"\nstats_suffix = "_stats"\n'
    )
    cfg = load(path)
    assert str(cfg.timezone) == "UTC"
    assert cfg.page_id(date(2026, 1, 2)) == "diary:2026-1-2_stats"


def test_php_date():
    day = date(2026, 3, 4)
    assert php_date("Y:m:Y-m-d", day) == "2026:03:2026-03-04"
    assert php_date("y/n/j", day) == "26/3/4"
    assert php_date("\\W\\e\\e\\k-d", day) == "Week-04"


def test_unsupported_php_date_character(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text('[diary]\nformat = "Y-W"\n')
    with pytest.raises(ConfigError, match="'W'"):
        load(path)


def test_empty_namespace(cfg):
    cfg = dataclasses.replace(cfg, diary_namespace="")
    assert cfg.page_id(date(2026, 10, 7)) == "2026:10:2026-10-07:stats"
    assert cfg.alert_backends == ("log",)


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
    import os

    assert os.environ["DIARYSTATS_TEST_A"] == "x=1"
    assert os.environ["DIARYSTATS_TEST_B"] == "from-env"
    monkeypatch.delenv("DIARYSTATS_TEST_A")
