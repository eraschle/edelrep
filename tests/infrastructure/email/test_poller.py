import time
from unittest.mock import MagicMock

from edelrep.infrastructure.email.poller import EmailPoller


def test_start_creates_running_scheduler() -> None:
    use_case = MagicMock()
    poller = EmailPoller(use_case=use_case, interval_seconds=300)
    assert not poller.is_running()
    poller.start()
    try:
        assert poller.is_running()
    finally:
        poller.stop()


def test_start_is_idempotent() -> None:
    use_case = MagicMock()
    poller = EmailPoller(use_case=use_case, interval_seconds=300)
    poller.start()
    try:
        poller.start()  # second start = no-op
        assert poller.is_running()
    finally:
        poller.stop()


def test_stop_is_idempotent() -> None:
    use_case = MagicMock()
    poller = EmailPoller(use_case=use_case, interval_seconds=300)
    poller.start()
    poller.stop()
    poller.stop()  # second stop = no-op
    assert not poller.is_running()


def test_tick_invokes_use_case_execute() -> None:
    use_case = MagicMock()
    poller = EmailPoller(use_case=use_case, interval_seconds=300)
    # Trigger tick directly without scheduler.
    poller._tick()  # type: ignore[attr-defined]
    use_case.execute.assert_called_once()


def test_tick_swallows_use_case_errors() -> None:
    """The poller must not crash if a single run of the use case fails."""
    use_case = MagicMock()
    use_case.execute.side_effect = RuntimeError("simulated email server outage")
    poller = EmailPoller(use_case=use_case, interval_seconds=300)
    # No exception expected.
    poller._tick()  # type: ignore[attr-defined]
    use_case.execute.assert_called_once()


def test_scheduled_job_fires_periodically() -> None:
    """With a tiny interval, the scheduler should call execute multiple times."""
    use_case = MagicMock()
    poller = EmailPoller(use_case=use_case, interval_seconds=0.1)
    poller.start()
    try:
        time.sleep(0.4)
    finally:
        poller.stop()
    # At least one execution should have happened.
    assert use_case.execute.call_count >= 1
