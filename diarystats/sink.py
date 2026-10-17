"""Output sinks for rendered stats pages.

Only a file sink exists now. A DokuWiki writer comes later and must keep
the same interface.
"""

import logging
from pathlib import Path
from typing import Protocol

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
