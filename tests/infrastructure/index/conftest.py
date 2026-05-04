import sqlite3
import threading
from collections.abc import Iterator

import pytest

from edelrep.infrastructure.index.connection import open_index_database


@pytest.fixture
def conn_with_lock() -> Iterator[tuple[sqlite3.Connection, threading.RLock]]:
    connection, lock = open_index_database(":memory:")
    yield connection, lock
    connection.close()


@pytest.fixture
def conn(conn_with_lock: tuple[sqlite3.Connection, threading.RLock]) -> sqlite3.Connection:
    return conn_with_lock[0]


@pytest.fixture
def lock(conn_with_lock: tuple[sqlite3.Connection, threading.RLock]) -> threading.RLock:
    return conn_with_lock[1]
