import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from edelrep.application.ingest_email import IngestEmailUseCase

_logger = logging.getLogger(__name__)


class EmailPoller:
    """Wraps APScheduler's BackgroundScheduler to poll the IMAP inbox periodically."""

    def __init__(
        self,
        *,
        use_case: IngestEmailUseCase,
        interval_seconds: float = 300.0,
    ) -> None:
        self._use_case = use_case
        self._interval_seconds = interval_seconds
        self._scheduler: BackgroundScheduler | None = None

    def start(self) -> None:
        if self._scheduler is not None:
            return
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            self._tick,
            trigger=IntervalTrigger(seconds=self._interval_seconds),  # type: ignore[arg-type]
            id="edelrep.email.poll",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.start()
        self._scheduler = scheduler

    def stop(self) -> None:
        if self._scheduler is None:
            return
        self._scheduler.shutdown(wait=False)
        self._scheduler = None

    def is_running(self) -> bool:
        return self._scheduler is not None

    def _tick(self) -> None:
        try:
            self._use_case.execute()
        except Exception:
            _logger.exception("email poll failed")
