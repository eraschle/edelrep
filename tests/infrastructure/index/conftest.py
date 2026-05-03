import sqlite3
from collections.abc import Iterator

import pytest

from edelrep.infrastructure.index.connection import open_index_database


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection = open_index_database(":memory:")
    yield connection
    connection.close()
