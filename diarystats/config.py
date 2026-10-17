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
SYSTEM_CONFIG_DIR = Path("/etc/diarystats")
# The first file that exists is used.
DEFAULT_CONFIGS = (CONFIG_DIR / "config.toml", SYSTEM_CONFIG_DIR / "config.toml")
DEFAULT_ENV_FILES = (CONFIG_DIR / "env", SYSTEM_CONFIG_DIR / "env")

RESCUETIME_KEY_VAR = "DIARYSTATS_RESCUETIME_KEY"

KNOWN_SINKS = ("file",)

# The page name strategies of the yearbox plugin, which creates the diary
# pages. Keys are the values of its "namestructure" setting. The plugin uses
# YearMonthCombinedNS for all other values.
_YEARBOX = {
    "separatedCompletely": lambda ns, y, m, d, name: f"{ns}:{y}:{m}:{d}",
    "YearMonthSeperatedNS": lambda ns, y, m, d, name: f"{ns}:{y}:{m}:{name}{y}-{m}-{d}",
    "YearNS": lambda ns, y, m, d, name: f"{ns}:{y}:{name}{y}-{m}-{d}",
    "default": lambda ns, y, m, d, name: f"{ns}:{y}-{m}:{name}{y}-{m}-{d}",
}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    timezone: ZoneInfo
    archive_dir: Path
    throttle_seconds: float
    diary_namespace: str
    diary_namestructure: str
    diary_name: str
    stats_suffix: str
    garmin_link: str
    rescuetime_link: str
    garmin_tokenstore: Path
    sink_kind: str
    sink_dir: Path
    alert_backends: tuple[str, ...]

    def page_id(self, day: date) -> str:
        """Return the ID of the stats page for the diary page of the day.

        The diary page ID is the same as the one of the yearbox plugin.
        """
        strategy = _YEARBOX.get(self.diary_namestructure, _YEARBOX["default"])
        name = f"{self.diary_name}-" if self.diary_name else ""
        base = strategy(self.diary_namespace, f"{day:%Y}", f"{day:%m}", f"{day:%d}", name)
        return base.lstrip(":") + self.stats_suffix


def _path(value: str) -> Path:
    return Path(value).expanduser()


def load(path: Path | None = None) -> Config:
    """Load the config file. Use defaults if no default file exists."""
    if path is None:
        path = next((p for p in DEFAULT_CONFIGS if p.exists()), None)
        raw = tomllib.loads(path.read_text()) if path else {}
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

    namestructure = diary.get("namestructure", "YearMonthSeperatedNS")
    if namestructure not in _YEARBOX:
        raise ConfigError(f"unknown yearbox namestructure: {namestructure}")

    return Config(
        timezone=ZoneInfo(raw.get("timezone", "Europe/Berlin")),
        archive_dir=_path(raw.get("archive_dir", "~/lifelog")),
        throttle_seconds=float(raw.get("throttle_seconds", 3)),
        diary_namespace=diary.get("namespace", "appreciation"),
        diary_namestructure=namestructure,
        diary_name=diary.get("name", ""),
        stats_suffix=diary.get("stats_suffix", ":stats"),
        garmin_link=links.get("garmin", ""),
        rescuetime_link=links.get("rescuetime", ""),
        garmin_tokenstore=_path(garmin.get("tokenstore", str(CONFIG_DIR / "garmin-tokens"))),
        sink_kind=sink_kind,
        sink_dir=_path(sink.get("dir", "~/.local/share/diarystats/rendered")),
        alert_backends=tuple(alert.get("backends", ["log"])),
    )


def load_env_file(path: Path | None = None) -> None:
    """Read KEY=VALUE lines into os.environ. Existing variables have priority.

    Without a path, use the first of DEFAULT_ENV_FILES that exists.
    """
    if path is None:
        path = next((p for p in DEFAULT_ENV_FILES if p.exists()), None)
    if path is None or not path.exists():
        return
    # The system setup uses root:diarystats 0640, so only check "other".
    if path.stat().st_mode & 0o007:
        log.warning("%s is readable by all users. Remove the access for others.", path)
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def rescuetime_key() -> str | None:
    return os.environ.get(RESCUETIME_KEY_VAR) or None
