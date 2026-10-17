import io
import json
import urllib.error
from datetime import date

import pytest

from diarystats.fetch.rescuetime import RescueTimeError, RescueTimeSource


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _opener(*outcomes):
    calls = []

    def opener(url, timeout):
        calls.append(url)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return Response(json.dumps(outcome).encode())

    opener.calls = calls
    return opener


def _http_error(code):
    return urllib.error.HTTPError("https://example/?key=SECRET", code, "x", {}, None)


def test_rows_by_date():
    opener = _opener([{"date": "2026-10-16", "total_hours": 1}, {"nodate": 1}])
    rows = RescueTimeSource("k", opener=opener, sleep=lambda s: None).fetch_summary()
    assert rows == {date(2026, 10, 16): {"date": "2026-10-16", "total_hours": 1}}


def test_retry_on_server_error():
    opener = _opener(_http_error(503), [{"date": "2026-10-16"}])
    rows = RescueTimeSource("k", opener=opener, sleep=lambda s: None).fetch_summary()
    assert len(opener.calls) == 2
    assert date(2026, 10, 16) in rows


def test_no_retry_on_auth_error_and_no_key_in_message():
    opener = _opener(_http_error(403))
    with pytest.raises(RescueTimeError) as e:
        RescueTimeSource("SECRET", opener=opener, sleep=lambda s: None).fetch_summary()
    assert len(opener.calls) == 1
    assert "SECRET" not in str(e.value)
    assert e.value.__cause__ is None


def test_message_with_http_200():
    opener = _opener({"message": "Please wait 5 minutes."})
    with pytest.raises(RescueTimeError, match="Please wait 5 minutes"):
        RescueTimeSource("k", opener=opener, sleep=lambda s: None).fetch_summary()
