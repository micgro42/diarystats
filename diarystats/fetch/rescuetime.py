"""Fetch daily summaries from the RescueTime analytic API."""

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import date
from typing import Any, Callable
from urllib.parse import urlencode

log = logging.getLogger(__name__)

FEED_URL = "https://www.rescuetime.com/anapi/daily_summary_feed"
RETRY_DELAYS = (5, 20, 60)
TIMEOUT = 30


class RescueTimeError(Exception):
    pass


class RescueTimeSource:
    def __init__(
        self,
        api_key: str,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.api_key = api_key
        self.opener = opener
        self.sleep = sleep

    def fetch_summary(self) -> dict[date, dict[str, Any]]:
        """Fetch the feed (about 14 days). Return {day: row}."""
        # The URL contains the API key. Do not log the URL.
        url = f"{FEED_URL}?{urlencode({'key': self.api_key})}"
        for delay in (*RETRY_DELAYS, None):
            try:
                with self.opener(url, timeout=TIMEOUT) as response:
                    data = json.load(response)
                break
            except urllib.error.HTTPError as e:
                retry = e.code == 429 or e.code >= 500
                if not retry or delay is None:
                    raise RescueTimeError(f"HTTP {e.code}") from None
                log.warning("rescuetime: HTTP %d. Retry in %d s.", e.code, delay)
            except (urllib.error.URLError, TimeoutError) as e:
                reason = getattr(e, "reason", e)
                if delay is None:
                    raise RescueTimeError(f"connection failed: {reason}") from None
                log.warning("rescuetime: %s. Retry in %d s.", reason, delay)
            except json.JSONDecodeError as e:
                raise RescueTimeError(f"invalid JSON: {e}") from None
            self.sleep(delay)

        if isinstance(data, dict) and "message" in data:
            # RescueTime sends rate limit messages with HTTP 200.
            raise RescueTimeError(f"RescueTime says: {data['message']}")
        if not isinstance(data, list):
            raise RescueTimeError(f"unexpected response type: {type(data).__name__}")
        rows = {}
        for row in data:
            try:
                rows[date.fromisoformat(str(row["date"])[:10])] = row
            except (KeyError, TypeError, ValueError):
                log.warning("rescuetime: skip row without valid date")
        return rows
