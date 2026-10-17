"""Send alerts. Only the log backend exists now. ntfy and email come later."""

import logging

log = logging.getLogger("diarystats.alert")

KNOWN_BACKENDS = ("log",)


class Alerter:
    def __init__(self, backends: tuple[str, ...] = ("log",)):
        unknown = set(backends) - set(KNOWN_BACKENDS)
        if unknown:
            raise ValueError(f"unknown alert backends: {', '.join(sorted(unknown))}")
        self.backends = backends
        self.sent: list[str] = []

    def alert(self, message: str) -> None:
        """Send the message to all backends. Do not put health data in it."""
        self.sent.append(message)
        if "log" in self.backends:
            # Keep the "ALERT:" prefix. Other tools grep the journal for it.
            log.error("ALERT: %s", message)
