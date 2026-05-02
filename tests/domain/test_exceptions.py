import pytest

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
    err = RepairNotFound("01J9TGZP6X2K0V3W7Y8Z4QABCD")
    assert err.repair_id == "01J9TGZP6X2K0V3W7Y8Z4QABCD"


def test_image_not_found_carries_id() -> None:
    err = ImageNotFound("01J9TGZP6X2K0V3W7Y8Z4QIMAGE")
    assert err.image_id == "01J9TGZP6X2K0V3W7Y8Z4QIMAGE"


def test_duplicate_vehicle_carries_id() -> None:
    err = DuplicateVehicle("12345")
    assert err.registration_number == "12345"
