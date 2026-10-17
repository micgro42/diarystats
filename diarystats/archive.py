"""Store raw API responses per day as JSON, with a meta.json and git history.

Layout: <root>/YYYY/MM/DD/{<source>_<name>.json, meta.json}
"""

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

log = logging.getLogger(__name__)

SOURCES = ("garmin", "rescuetime")

# The archive repo uses a fixed identity. It does not depend on the git
# config of the user that runs the job.
GIT_IDENTITY = ["-c", "user.name=diarystats", "-c", "user.email=diarystats@localhost"]


@dataclass
class SourceResult:
    """The result of one fetch for one source and one day.

    files is None if no data is available. error is set if the fetch failed.
    """

    files: dict[str, Any] | None
    complete: bool = False
    error: str | None = None
    info: dict[str, Any] = field(default_factory=dict)


@dataclass
class DayData:
    """All archived data for one day: files[source][name] and meta[source]."""

    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    meta: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_results(cls, results: dict[str, SourceResult]) -> "DayData":
        data = cls()
        for source, result in results.items():
            data.files[source] = result.files or {}
            data.meta[source] = {"complete": result.complete, "error": result.error}
        return data


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dump(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


class Archive:
    def __init__(self, root: Path):
        self.root = root

    def day_dir(self, day: date) -> Path:
        return self.root / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}"

    def rel_day_dir(self, day: date) -> str:
        return f"{self.root.name}/{day:%Y}/{day:%m}/{day:%d}"

    def _read_meta(self, day: date) -> dict[str, dict[str, Any]]:
        path = self.day_dir(day) / "meta.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def apply(self, day: date, source: str, result: SourceResult) -> None:
        """Write a fetch result to the archive.

        New data replaces old data. A failed fetch or a fetch without data
        does not delete old data. It only updates meta.json.
        """
        directory = self.day_dir(day)
        directory.mkdir(parents=True, exist_ok=True)
        meta = self._read_meta(day)
        entry = meta.get(source, {"complete": False})

        if result.files:
            for name, obj in result.files.items():
                _dump(directory / f"{source}_{name}.json", obj)
            entry = {
                "fetched_at": _now(),
                "complete": result.complete,
                "error": None,
                **result.info,
            }
        else:
            entry["checked_at"] = _now()
            entry["error"] = result.error

        meta[source] = entry
        _dump(directory / "meta.json", meta)

    def load(self, day: date) -> DayData:
        directory = self.day_dir(day)
        data = DayData(meta=self._read_meta(day))
        for source in SOURCES:
            data.files[source] = {}
            for path in sorted(directory.glob(f"{source}_*.json")):
                name = path.stem[len(source) + 1:]
                data.files[source][name] = json.loads(path.read_text())
        return data

    def is_complete(self, day: date, source: str) -> bool:
        return bool(self._read_meta(day).get(source, {}).get("complete"))

    def days(self) -> Iterator[date]:
        """Yield all archived days in order."""
        pattern = re.compile(r"^\d{4}/\d{2}/\d{2}$")
        found = []
        for meta in self.root.glob("*/*/*/meta.json"):
            rel = meta.parent.relative_to(self.root).as_posix()
            if pattern.match(rel):
                found.append(date.fromisoformat(rel.replace("/", "-")))
        yield from sorted(found)

    def commit(self, message: str) -> bool:
        """Commit all changes in the archive. Return False if nothing changed."""
        self.root.mkdir(parents=True, exist_ok=True)
        if not (self.root / ".git").exists():
            self._git("init", "-q")
        self._git("add", "-A")
        staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=self.root, check=False
        )
        if staged.returncode == 0:
            log.info("archive: no changes to commit")
            return False
        self._git(*GIT_IDENTITY, "commit", "-q", "-m", message)
        return True

    def _git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, check=True)
