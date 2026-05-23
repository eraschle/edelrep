from datetime import UTC, date, datetime

import pytest
from hypothesis import given, settings, strategies as st
from ulid import ULID

from edelrep.domain.entities import Image, ImageSource, Repair, Vehicle
from edelrep.infrastructure.filesystem import (
    FilesystemImageRepository,
    FilesystemRepairRepository,
    FilesystemVehicleRepository,
)
from edelrep.infrastructure.index.connection import open_index_database
from edelrep.infrastructure.index.projector import SqliteIndexProjector
from edelrep.infrastructure.storage import LocalFilesystemBackend


@settings(deadline=None, max_examples=10)
@given(
    vehicle_count=st.integers(min_value=0, max_value=3),
    repairs_per_vehicle=st.integers(min_value=0, max_value=2),
    images_per_repair=st.integers(min_value=0, max_value=2),
)
def test_full_rebuild_matches_input_graph(
    tmp_path_factory: pytest.TempPathFactory,
    vehicle_count: int,
    repairs_per_vehicle: int,
    images_per_repair: int,
) -> None:
    root = tmp_path_factory.mktemp("graph")
    backend = LocalFilesystemBackend(root / "store")
    vrepo = FilesystemVehicleRepository(backend)
    rrepo = FilesystemRepairRepository(backend)
    irepo = FilesystemImageRepository(backend)

    expected_repair_count = vehicle_count * repairs_per_vehicle
    expected_image_count = expected_repair_count * images_per_repair
    saved_regs: list[str] = []
    for vi in range(vehicle_count):
        reg = f"VEH{vi:04d}"
        saved_regs.append(reg)
        vehicle = Vehicle(
            id=ULID(),
            registration_number=reg,
            vin=f"VIN-{reg}",
            description=f"Vehicle {reg}",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        vrepo.save(vehicle)
        for ri in range(repairs_per_vehicle):
            repair = Repair(
                id=ULID(),
                vehicle_id=vehicle.id,
                date=date(2026, 1, ri + 1),
                description=f"repair-{ri}",
                created_at=datetime(2026, 1, ri + 1, tzinfo=UTC),
            )
            rrepo.save(repair)
            for _ in range(images_per_repair):
                irepo.save(
                    Image(
                        id=ULID(),
                        repair_id=repair.id,
                        storage_key="",
                        thumbnail_key=None,
                        filename="0001.jpg",
                        mime_type="image/jpeg",
                        size_bytes=4,
                        source=ImageSource.MANUAL,
                        uploaded_at=datetime(2026, 1, ri + 1, tzinfo=UTC),
                        captured_at=None,
                    ),
                    raw_bytes=b"\xff\xd8\xff\xd9",
                )

    conn, lock = open_index_database(":memory:")
    try:
        projector = SqliteIndexProjector(conn, lock)
        stats = projector.full_rebuild(vrepo, rrepo, irepo)

        assert stats.vehicles_indexed == vehicle_count
        assert stats.repairs_indexed == expected_repair_count
        assert stats.images_indexed == expected_image_count

        cur = conn.execute("SELECT COUNT(*) FROM vehicles")
        assert cur.fetchone()[0] == vehicle_count
        cur = conn.execute("SELECT COUNT(*) FROM repairs")
        assert cur.fetchone()[0] == expected_repair_count
        cur = conn.execute("SELECT COUNT(*) FROM images")
        assert cur.fetchone()[0] == expected_image_count

        for reg in saved_regs:
            cur = conn.execute(
                "SELECT registration_number FROM vehicles_fts WHERE vehicles_fts MATCH ?",
                (f"{reg}*",),
            )
            rows = cur.fetchall()
            assert any(row[0] == reg for row in rows)
    finally:
        conn.close()
