import sqlite3
import threading
from collections.abc import Iterator

import pytest

from edelrep.infrastructure.index.connection import open_index_database


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection, _lock = open_index_database(":memory:")
    yield connection
    connection.close()


@pytest.fixture
def lock() -> threading.RLock:
    return threading.RLock()


@pytest.fixture
def conn_with_lock() -> Iterator[tuple[sqlite3.Connection, threading.RLock]]:
    connection, lock = open_index_database(":memory:")
    yield connection, lock
    connection.close()
