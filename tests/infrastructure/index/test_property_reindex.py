from datetime import UTC, date, datetime

import pytest
from hypothesis import given, settings, strategies as st
from ulid import ULID

from edelrep.domain.entities import Repair, Vehicle
from edelrep.domain.value_objects import VehicleId
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.index.connection import open_index_database
from edelrep.infrastructure.index.projector import SqliteIndexProjector
from edelrep.infrastructure.storage import LocalFilesystemBackend


@settings(deadline=None, max_examples=15)
@given(
    vehicle_count=st.integers(min_value=0, max_value=4),
    repairs_per_vehicle=st.integers(min_value=0, max_value=3),
)
def test_full_rebuild_matches_input_graph(
    tmp_path_factory: pytest.TempPathFactory,
    vehicle_count: int,
    repairs_per_vehicle: int,
) -> None:
    root = tmp_path_factory.mktemp("graph")
    backend = LocalFilesystemBackend(root / "store")
    vrepo = FilesystemVehicleRepository(backend)
    rrepo = FilesystemRepairRepository(backend)
    irepo = FilesystemImageRepository(backend)

    expected_repair_count = vehicle_count * repairs_per_vehicle
    for vi in range(vehicle_count):
        reg = f"VEH{vi:04d}"
        vrepo.save(
            Vehicle(
                id=VehicleId(reg),
                vin=f"VIN-{reg}",
                description=f"Vehicle {reg}",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        for ri in range(repairs_per_vehicle):
            rrepo.save(
                Repair(
                    id=ULID(),
                    vehicle_id=VehicleId(reg),
                    date=date(2026, 1, ri + 1),
                    description=f"repair-{ri}",
                    created_at=datetime(2026, 1, ri + 1, tzinfo=UTC),
                )
            )

    conn = open_index_database(":memory:")
    projector = SqliteIndexProjector(conn)
    stats = projector.full_rebuild(vrepo, rrepo, irepo)

    assert stats.vehicles_indexed == vehicle_count
    assert stats.repairs_indexed == expected_repair_count

    cur = conn.execute("SELECT COUNT(*) FROM vehicles")
    assert cur.fetchone()[0] == vehicle_count
    cur = conn.execute("SELECT COUNT(*) FROM repairs")
    assert cur.fetchone()[0] == expected_repair_count

    # FTS5 sanity: each vehicle's reg_no is searchable.
    for vi in range(vehicle_count):
        reg = f"VEH{vi:04d}"
        cur = conn.execute(
            "SELECT registration_number FROM vehicles_fts WHERE vehicles_fts MATCH ?",
            (f"{reg}*",),
        )
        rows = cur.fetchall()
        assert any(row[0] == reg for row in rows)
