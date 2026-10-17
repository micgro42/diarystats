"""Fetch daily data from Garmin Connect with python-garminconnect.

The API is unofficial. Expect breakage after changes at Garmin.

The library retries 5xx and network errors itself. It fails at once on 429.
This module does not retry: the next daily run fetches the day again.
"""

import importlib.metadata
import logging
import time
from datetime import date
from getpass import getpass
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

# One call for each archive file. The key is the file name: garmin_<key>.json
ENDPOINTS: dict[str, Callable[[Any, str], Any]] = {
    "sleep": lambda c, d: c.get_sleep_data(d),
    "stats": lambda c, d: c.get_stats(d),
    "body_battery": lambda c, d: c.get_body_battery(d, d),
    "hrv": lambda c, d: c.get_hrv_data(d),
}

# The library writes this file in the tokenstore directory, mode 0600.
TOKEN_FILE = "garmin_tokens.json"


class GarminAuthError(Exception):
    """The stored tokens do not work. Run login-garmin again."""


class GarminFetchError(Exception):
    pass


class _Never(Exception):
    """Stands in for exception classes that the library does not have."""


def library_version() -> str:
    try:
        return importlib.metadata.version("garminconnect")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _has_tokens(tokenstore: Path) -> bool:
    return (tokenstore / TOKEN_FILE).is_file()


def login_interactive(tokenstore: Path, email: str) -> None:
    """Log in with password and optional MFA code. Store only the tokens."""
    import garminconnect

    tokenstore.mkdir(mode=0o700, parents=True, exist_ok=True)
    client = garminconnect.Garmin(
        email,
        getpass("Garmin password: "),
        prompt_mfa=lambda: input("MFA code: ").strip(),
    )
    client.login(str(tokenstore))
    # The library ignores errors when it writes the tokens. Make sure they exist.
    if not _has_tokens(tokenstore):
        raise GarminAuthError(f"login worked, but no {TOKEN_FILE} in {tokenstore}")


class GarminSource:
    def __init__(
        self,
        tokenstore: Path,
        pause: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.tokenstore = tokenstore
        self.pause = pause
        self.sleep = sleep
        self._client: Any = None
        self._lib: Any = None

    def _login(self) -> Any:
        try:
            import garminconnect
        except ImportError as e:
            raise GarminFetchError(f"cannot import garminconnect: {e}") from e
        self._lib = garminconnect

        if not _has_tokens(self.tokenstore):
            raise GarminAuthError(f"no tokens in {self.tokenstore}. Run login-garmin.")
        auth_error = getattr(garminconnect, "GarminConnectAuthenticationError", _Never)
        try:
            # Without credentials, the library cannot fall back to a password
            # login. Rejected tokens thus cause an authentication error.
            client = garminconnect.Garmin()
            client.login(str(self.tokenstore))
        except auth_error as e:
            raise GarminAuthError(f"login with stored tokens failed: {e}") from e
        except Exception as e:
            raise GarminFetchError(f"login failed: {e}") from e
        self._client = client
        return client

    def fetch(self, day: date) -> dict[str, Any]:
        """Fetch all endpoints for one day. Return {name: raw response}."""
        client = self._client or self._login()
        result = {}
        for name, call in ENDPOINTS.items():
            result[name] = self._call(name, call, client, day.isoformat())
            self.sleep(self.pause)
        return result

    def _call(self, name: str, call: Callable, client: Any, day: str) -> Any:
        lib = self._lib
        auth_error = getattr(lib, "GarminConnectAuthenticationError", _Never)
        not_found = getattr(lib, "GarminConnectNotFoundError", _Never)
        try:
            return call(client, day)
        except auth_error as e:
            raise GarminAuthError(f"{name}: {e}") from e
        except not_found:
            log.info("garmin %s %s: no data (404)", name, day)
            return None
        except Exception as e:
            raise GarminFetchError(f"{name}: {e}") from e
