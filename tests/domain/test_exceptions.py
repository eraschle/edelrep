import pytest
from ulid import ULID

from edelrep.domain.exceptions import (
    DomainError,
    DuplicateVehicle,
    ImageNotFound,
    InvalidVehicleId,
    RepairNotFound,
    VehicleNotFound,
)


@pytest.mark.parametrize(
    "exc_cls",
    [InvalidVehicleId, VehicleNotFound, RepairNotFound, ImageNotFound, DuplicateVehicle],
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
