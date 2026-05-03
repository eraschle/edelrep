import threading
import time

from edelrep.infrastructure.watcher.debouncer import Debouncer


def test_single_event_flushes_after_window() -> None:
    flushed: list[set[str]] = []
    d = Debouncer(window_seconds=0.05, on_flush=flushed.append)
    d.add("a")
    time.sleep(0.15)
    assert flushed == [{"a"}]


def test_multiple_events_within_window_dedupe() -> None:
    flushed: list[set[str]] = []
    d = Debouncer(window_seconds=0.05, on_flush=flushed.append)
    d.add("a")
    d.add("b")
    d.add("a")
    time.sleep(0.15)
    assert flushed == [{"a", "b"}]


def test_events_after_flush_start_a_new_batch() -> None:
    flushed: list[set[str]] = []
    d = Debouncer(window_seconds=0.05, on_flush=flushed.append)
    d.add("a")
    time.sleep(0.15)
    d.add("b")
    time.sleep(0.15)
    assert flushed == [{"a"}, {"b"}]


def test_flush_now_fires_immediately() -> None:
    flushed: list[set[str]] = []
    d = Debouncer(window_seconds=10.0, on_flush=flushed.append)
    d.add("a")
    d.flush_now()
    assert flushed == [{"a"}]


def test_flush_now_with_empty_buffer_does_not_call_callback() -> None:
    flushed: list[set[str]] = []
    d = Debouncer(window_seconds=10.0, on_flush=flushed.append)
    d.flush_now()
    assert flushed == []


def test_stop_cancels_pending_flush() -> None:
    flushed: list[set[str]] = []
    d = Debouncer(window_seconds=0.05, on_flush=flushed.append)
    d.add("a")
    d.stop()
    time.sleep(0.15)
    assert flushed == []


def test_thread_safety_under_concurrent_adds() -> None:
    flushed: list[set[str]] = []
    d = Debouncer(window_seconds=0.1, on_flush=flushed.append)

    def worker(prefix: str) -> None:
        for i in range(50):
            d.add(f"{prefix}-{i}")

    threads = [threading.Thread(target=worker, args=(p,)) for p in ("a", "b", "c")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    time.sleep(0.5)
    assert len(flushed) >= 1
    total_keys: set[str] = set().union(*flushed)
    assert len(total_keys) == 150
