"""Output sinks for rendered stats pages."""

import logging
import subprocess
from pathlib import Path
from typing import Callable, Protocol

log = logging.getLogger(__name__)


class Sink(Protocol):
    def write(self, page_id: str, text: str) -> bool:
        """Write the page. Return True if the content changed."""
        ...


class FileSink:
    """Write each page to <dir>/<namespace path>/<page>.txt, as DokuWiki does."""

    def __init__(self, directory: Path):
        self.directory = directory

    def path(self, page_id: str) -> Path:
        return self.directory / (page_id.replace(":", "/") + ".txt")

    def write(self, page_id: str, text: str) -> bool:
        path = self.path(page_id)
        if path.exists() and path.read_text() == text:
            log.info("sink: %s unchanged", page_id)
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        log.info("sink: wrote %s", path)
        return True


class DwpageSink:
    """Save pages with DokuWiki's bin/dwpage.php.

    The command gets the page ID as its last argument and the text on stdin.
    Use deploy/diarystats-wiki-commit through sudo, so that the job can only
    commit stats pages as the web server user.

    DokuWiki also skips a save if the text is unchanged. The local compare
    prevents the sudo call and the page lock on most days.
    """

    def __init__(
        self,
        pages_dir: Path,
        command: tuple[str, ...],
        run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ):
        self.pages_dir = pages_dir
        self.command = command
        self.run = run

    def path(self, page_id: str) -> Path:
        return self.pages_dir / (page_id.replace(":", "/") + ".txt")

    def write(self, page_id: str, text: str) -> bool:
        path = self.path(page_id)
        try:
            if path.read_text() == text:
                log.info("sink: %s unchanged", page_id)
                return False
        except FileNotFoundError:
            pass
        try:
            result = self.run(
                [*self.command, page_id],
                input=text,
                text=True,
                capture_output=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired as e:
            raise OSError(f"dwpage: timeout for {page_id}") from e
        if result.returncode != 0:
            raise OSError(f"dwpage: {page_id}: {(result.stderr or result.stdout).strip()}")
        log.info("sink: saved %s", page_id)
        return True


def make_sink(cfg) -> Sink:
    if cfg.sink_kind == "dwpage":
        return DwpageSink(cfg.dokuwiki_pages_dir, cfg.dwpage_command)
    return FileSink(cfg.sink_dir)
