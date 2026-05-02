from ulid import ULID


class DomainError(Exception):
    """Base class for all domain-level errors."""


class InvalidVehicleId(DomainError):
    """Raised when a registration number does not match the allowed pattern."""

    def __init__(self, value: str) -> None:
        super().__init__(f"Invalid vehicle registration number: {value!r}")
        self.value = value


class VehicleNotFound(DomainError):
    """Raised when a vehicle lookup misses."""

    def __init__(self, registration_number: str) -> None:
        super().__init__(f"Vehicle not found: {registration_number!r}")
        self.registration_number = registration_number


class DuplicateVehicle(DomainError):
    """Raised when creating a vehicle that already exists."""

    def __init__(self, registration_number: str) -> None:
        super().__init__(f"Vehicle already exists: {registration_number!r}")
        self.registration_number = registration_number


class RepairNotFound(DomainError):
    """Raised when a repair lookup misses."""

    def __init__(self, repair_id: ULID) -> None:
        super().__init__(f"Repair not found: {repair_id!s}")
        self.repair_id = repair_id


class ImageNotFound(DomainError):
    """Raised when an image lookup misses."""

    def __init__(self, image_id: ULID) -> None:
        super().__init__(f"Image not found: {image_id!s}")
        self.image_id = image_id
