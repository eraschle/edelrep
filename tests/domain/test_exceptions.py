import pytest
from ulid import ULID

from edelrep.domain.exceptions import (
    DomainError,
    DuplicateRepair,
    DuplicateVehicle,
    ImageNotFound,
    InvalidVehicleId,
    RepairNotFound,
    SidecarSchemaError,
    VehicleNotFound,
)


@pytest.mark.parametrize(
    "exc_cls",
    [
        InvalidVehicleId,
        VehicleNotFound,
        RepairNotFound,
        ImageNotFound,
        DuplicateVehicle,
        DuplicateRepair,
        SidecarSchemaError,
    ],
)
def test_all_inherit_from_domain_error(exc_cls: type[Exception]) -> None:
    assert issubclass(exc_cls, DomainError)


def test_vehicle_not_found_carries_id() -> None:
    err = VehicleNotFound("12345")
    assert err.registration_number == "12345"
    assert "12345" in str(err)


def test_repair_not_found_carries_id() -> None:
    rid = ULID()
    err = RepairNotFound(rid)
    assert err.repair_id is rid
    assert str(rid) in str(err)


def test_image_not_found_carries_id() -> None:
    iid = ULID()
    err = ImageNotFound(iid)
    assert err.image_id is iid
    assert str(iid) in str(err)


def test_duplicate_vehicle_carries_id() -> None:
    err = DuplicateVehicle("12345")
    assert err.registration_number == "12345"


def test_sidecar_schema_error_carries_fields() -> None:
    err = SidecarSchemaError("/x/_vehicle.json", expected=1, actual=2)
    assert err.path == "/x/_vehicle.json"
    assert err.expected == 1
    assert err.actual == 2
    assert "schema_version=1" in str(err)


def test_duplicate_repair_carries_fields() -> None:
    err = DuplicateRepair("12345", "2026-05-02__brakes")
    assert err.vehicle_id == "12345"
    assert err.folder_name == "2026-05-02__brakes"
