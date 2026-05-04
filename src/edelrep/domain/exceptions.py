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


class SidecarSchemaError(DomainError):
    """Raised when a sidecar file has an unsupported schema_version."""

    def __init__(self, path: str, expected: int, actual: int | None) -> None:
        super().__init__(f"Sidecar {path!r}: expected schema_version={expected}, got {actual!r}")
        self.path = path
        self.expected = expected
        self.actual = actual


class DuplicateRepair(DomainError):
    """Raised when creating a repair whose folder already exists."""

    def __init__(self, vehicle_id: str, folder_name: str) -> None:
        super().__init__(f"Repair folder already exists for vehicle {vehicle_id!r}: {folder_name!r}")
        self.vehicle_id = vehicle_id
        self.folder_name = folder_name


class DuplicateImage(DomainError):
    """Raised when uploading an image whose content matches an existing image in the same repair."""

    def __init__(self, repair_id: ULID, existing_filename: str) -> None:
        super().__init__(
            f"Identisches Bild ist bereits in Reparatur {repair_id!s} vorhanden ({existing_filename!r})"
        )
        self.repair_id = repair_id
        self.existing_filename = existing_filename
