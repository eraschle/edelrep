"""Background scheduler that runs the soft-delete cleanup once a day."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from edelrep.application.delete_vehicle import CleanupDeletedVehiclesUseCase

_logger = logging.getLogger(__name__)

_DEFAULT_HOUR = 3
_DEFAULT_MINUTE = 0


class DailyCleanupScheduler:
    """Runs ``cleanup_use_case`` once every 24 hours in a background thread.

    First run fires at the next occurrence of ``hour:minute`` in local time;
    subsequent runs fire 24 hours later. Stops cleanly on :meth:`stop`.
    """

    def __init__(
        self,
        cleanup_use_case: CleanupDeletedVehiclesUseCase,
        *,
        hour: int = _DEFAULT_HOUR,
        minute: int = _DEFAULT_MINUTE,
        retention_days: int = CleanupDeletedVehiclesUseCase.DEFAULT_RETENTION_DAYS,
    ) -> None:
        self._cleanup = cleanup_use_case
        self._hour = hour
        self._minute = minute
        self._retention_days = retention_days
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="edelrep-daily-cleanup",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            delay = self._seconds_until_next_fire()
            if self._stop.wait(delay):
                return
            try:
                stats = self._cleanup.execute(retention_days=self._retention_days)
                _logger.info("daily cleanup: purged %d vehicles", stats.vehicles_purged)
            except Exception:
                _logger.exception("daily cleanup: failed")

    def _seconds_until_next_fire(self) -> float:
        now = datetime.now().astimezone()
        target = now.replace(hour=self._hour, minute=self._minute, second=0, microsecond=0)
        if target <= now:
            target = target + timedelta(days=1)
        return max(1.0, (target - now).total_seconds())
