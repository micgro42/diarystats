import sys
import types
from datetime import date

import pytest

from diarystats.fetch.garmin import TOKEN_FILE, GarminAuthError, GarminFetchError, GarminSource


class ConnectionError_(Exception):
    pass


class NotFound(ConnectionError_):
    pass


class AuthError(Exception):
    pass


def _fake_lib(monkeypatch, client):
    """Install a stand-in for garminconnect with the same exception classes."""
    lib = types.ModuleType("garminconnect")
    lib.GarminConnectConnectionError = ConnectionError_
    lib.GarminConnectNotFoundError = NotFound
    lib.GarminConnectAuthenticationError = AuthError
    lib.Garmin = lambda: client
    monkeypatch.setitem(sys.modules, "garminconnect", lib)


class FakeClient:
    def __init__(self, login_error=None, hrv_error=None):
        self.login_error = login_error
        self.hrv_error = hrv_error

    def login(self, tokenstore):
        if self.login_error:
            raise self.login_error

    def get_sleep_data(self, d):
        return {"dailySleepDTO": {"calendarDate": d}}

    def get_stats(self, d):
        return {"totalSteps": 1}

    def get_body_battery(self, start, end):
        return [{"date": start}]

    def get_hrv_data(self, d):
        if self.hrv_error:
            raise self.hrv_error
        return {"hrvSummary": {}}


@pytest.fixture
def tokenstore(tmp_path):
    (tmp_path / TOKEN_FILE).write_text("{}")
    return tmp_path


def _source(tokenstore):
    return GarminSource(tokenstore, sleep=lambda s: None)


def test_fetch_all_endpoints(monkeypatch, tokenstore):
    _fake_lib(monkeypatch, FakeClient())
    files = _source(tokenstore).fetch(date(2026, 10, 16))
    assert set(files) == {"sleep", "stats", "body_battery", "hrv"}
    assert files["body_battery"] == [{"date": "2026-10-16"}]


def test_not_found_is_no_data(monkeypatch, tokenstore):
    _fake_lib(monkeypatch, FakeClient(hrv_error=NotFound("404")))
    assert _source(tokenstore).fetch(date(2026, 10, 16))["hrv"] is None


def test_other_errors_fail(monkeypatch, tokenstore):
    _fake_lib(monkeypatch, FakeClient(hrv_error=ConnectionError_("500")))
    with pytest.raises(GarminFetchError, match="hrv"):
        _source(tokenstore).fetch(date(2026, 10, 16))


def test_rejected_tokens(monkeypatch, tokenstore):
    _fake_lib(monkeypatch, FakeClient(login_error=AuthError("Username and password are required")))
    with pytest.raises(GarminAuthError):
        _source(tokenstore).fetch(date(2026, 10, 16))


def test_missing_token_file(monkeypatch, tmp_path):
    _fake_lib(monkeypatch, FakeClient())
    with pytest.raises(GarminAuthError, match="login-garmin"):
        _source(tmp_path).fetch(date(2026, 10, 16))
