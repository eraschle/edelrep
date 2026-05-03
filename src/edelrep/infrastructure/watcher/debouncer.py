import threading
from collections.abc import Callable


class Debouncer:
    """Buffers keys and flushes them as one batch after a quiet window.

    Thread-safe. Each call to :meth:`add` resets the timer; ``on_flush``
    is invoked once with the deduplicated set when the window elapses.
    """

    def __init__(self, window_seconds: float, on_flush: Callable[[set[str]], None]) -> None:
        self._window = window_seconds
        self._on_flush = on_flush
        self._lock = threading.Lock()
        self._buffer: set[str] = set()
        self._timer: threading.Timer | None = None

    def add(self, key: str) -> None:
        with self._lock:
            self._buffer.add(key)
            self._restart_timer_locked()

    def flush_now(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if not self._buffer:
                return
            batch = self._buffer
            self._buffer = set()
        self._on_flush(batch)

    def stop(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._buffer.clear()

    def _restart_timer_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(self._window, self._fire)
        self._timer.daemon = True
        self._timer.start()

    def _fire(self) -> None:
        with self._lock:
            if not self._buffer:
                self._timer = None
                return
            batch = self._buffer
            self._buffer = set()
            self._timer = None
        self._on_flush(batch)
