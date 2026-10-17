"""Load the TOML config and the secrets env file."""

import logging
import os
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

CONFIG_DIR = Path("~/.config/diarystats").expanduser()
DEFAULT_CONFIG = CONFIG_DIR / "config.toml"
DEFAULT_ENV_FILE = CONFIG_DIR / "env"

RESCUETIME_KEY_VAR = "DIARYSTATS_RESCUETIME_KEY"

KNOWN_SINKS = ("file",)

# The PHP date() format characters that diarystats supports. The today
# plugin uses PHP date() for the date part of the page ID.
_PHP_DATE = {
    "Y": lambda d: f"{d:%Y}",
    "y": lambda d: f"{d:%y}",
    "m": lambda d: f"{d:%m}",
    "n": lambda d: str(d.month),
    "d": lambda d: f"{d:%d}",
    "j": lambda d: str(d.day),
}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    timezone: ZoneInfo
    archive_dir: Path
    throttle_seconds: float
    diary_namespace: str
    diary_format: str
    stats_suffix: str
    garmin_link: str
    rescuetime_link: str
    garmin_tokenstore: Path
    sink_kind: str
    sink_dir: Path
    alert_backends: tuple[str, ...]

    def page_id(self, day: date) -> str:
        """Return the ID of the stats page for the diary page of the day.

        The diary page ID is built as in the today plugin:
        <namespace>:<date(format)>
        """
        base = f"{self.diary_namespace}:{php_date(self.diary_format, day)}"
        return base.lstrip(":") + self.stats_suffix


def php_date(fmt: str, day: date) -> str:
    """Format the day like PHP date(). Support only the characters in _PHP_DATE."""
    out = []
    chars = iter(fmt)
    for char in chars:
        if char == "\\":
            out.append(next(chars, ""))
        elif char in _PHP_DATE:
            out.append(_PHP_DATE[char](day))
        elif char.isascii() and char.isalpha():
            raise ConfigError(f"unsupported PHP date() character {char!r} in {fmt!r}")
        else:
            out.append(char)
    return "".join(out)


def _path(value: str) -> Path:
    return Path(value).expanduser()


def load(path: Path | None = None) -> Config:
    """Load the config file. Use defaults if the default file does not exist."""
    if path is None:
        path = DEFAULT_CONFIG
        raw = tomllib.loads(path.read_text()) if path.exists() else {}
    else:
        try:
            raw = tomllib.loads(path.read_text())
        except FileNotFoundError as e:
            raise ConfigError(f"config file not found: {path}") from e

    diary = raw.get("diary", {})
    links = raw.get("links", {})
    garmin = raw.get("garmin", {})
    sink = raw.get("sink", {})
    alert = raw.get("alert", {})

    sink_kind = sink.get("kind", "file")
    if sink_kind not in KNOWN_SINKS:
        raise ConfigError(f"unknown sink kind: {sink_kind}")

    diary_format = diary.get("format", "Y:m:Y-m-d")
    php_date(diary_format, date(2000, 1, 1))  # Fail early on a bad format.

    return Config(
        timezone=ZoneInfo(raw.get("timezone", "Europe/Berlin")),
        archive_dir=_path(raw.get("archive_dir", "~/lifelog")),
        throttle_seconds=float(raw.get("throttle_seconds", 3)),
        diary_namespace=diary.get("namespace", "appreciation"),
        diary_format=diary_format,
        stats_suffix=diary.get("stats_suffix", ":stats"),
        garmin_link=links.get("garmin", ""),
        rescuetime_link=links.get("rescuetime", ""),
        garmin_tokenstore=_path(garmin.get("tokenstore", str(CONFIG_DIR / "garmin-tokens"))),
        sink_kind=sink_kind,
        sink_dir=_path(sink.get("dir", "~/.local/share/diarystats/rendered")),
        alert_backends=tuple(alert.get("backends", ["log"])),
    )


def load_env_file(path: Path = DEFAULT_ENV_FILE) -> None:
    """Read KEY=VALUE lines into os.environ. Existing variables have priority."""
    if not path.exists():
        return
    if path.stat().st_mode & 0o077:
        log.warning("%s is readable by other users. Set mode 0600.", path)
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def rescuetime_key() -> str | None:
    return os.environ.get(RESCUETIME_KEY_VAR) or None
