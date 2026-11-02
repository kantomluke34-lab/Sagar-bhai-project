"""Transport-neutral reminder and follow-up scheduler."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone

from .storage import BotStore

LOGGER = logging.getLogger(__name__)


class NotificationScheduler:
    """Poll due notifications and record successful deliveries exactly once."""

    def __init__(
        self,
        store: BotStore,
        sender: Callable[[str, str], None],
        is_available: Callable[[], bool] | None = None,
        interval_seconds: int = 30,
    ) -> None:
        self.store = store
        self.sender = sender
        self.is_available = is_available or (lambda: True)
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run,
            name="meeting-notifications",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def run_once(self, now: datetime | None = None) -> int:
        if not self.is_available():
            return 0
        sent = 0
        for job in self.store.due_notifications(now or datetime.now(timezone.utc)):
            try:
                self.sender(str(job["phone"]), str(job["message"]))
                self.store.mark_notification_sent(job)
                sent += 1
            except Exception:
                LOGGER.exception(
                    "Failed to send %s for meeting %s",
                    job["notification_key"],
                    job["meeting_id"],
                )
        return sent

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                LOGGER.exception("Notification scheduler cycle failed")
            self._stop.wait(self.interval_seconds)
