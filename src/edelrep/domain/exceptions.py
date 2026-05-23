from ulid import ULID


class DomainError(Exception):
    """Base class for all domain-level errors."""


class InvalidRegistrationNumber(DomainError):
    """Raised when a Stammnummer does not match the allowed pattern."""

    def __init__(self, value: str) -> None:
        super().__init__(f"Ungültige Stammnummer: {value!r}")
        self.value = value


class InvalidVin(DomainError):
    """Raised when a Rahmennummer does not match the allowed pattern."""

    def __init__(self, value: str) -> None:
        super().__init__(f"Ungültige Rahmennummer: {value!r}")
        self.value = value


class VehicleIdentifierRequired(DomainError):
    """Raised when a vehicle is created without either Stammnummer or Rahmennummer."""

    def __init__(self) -> None:
        super().__init__("Stammnummer oder Rahmennummer muss angegeben werden.")


class VehicleNotFound(DomainError):
    """Raised when a vehicle lookup misses."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"Fahrzeug nicht gefunden: {identifier!r}")
        self.identifier = identifier


class DuplicateRegistrationNumber(DomainError):
    """Raised when saving a vehicle whose Stammnummer is already in use."""

    def __init__(self, value: str) -> None:
        super().__init__(f"Stammnummer ist bereits vergeben: {value!r}")
        self.value = value


class DuplicateVin(DomainError):
    """Raised when saving a vehicle whose Rahmennummer is already in use."""

    def __init__(self, value: str) -> None:
        super().__init__(f"Rahmennummer ist bereits vergeben: {value!r}")
        self.value = value


class RepairNotFound(DomainError):
    """Raised when a repair lookup misses."""

    def __init__(self, repair_id: ULID) -> None:
        super().__init__(f"Reparatur nicht gefunden: {repair_id!s}")
        self.repair_id = repair_id


class ImageNotFound(DomainError):
    """Raised when an image lookup misses."""

    def __init__(self, image_id: ULID) -> None:
        super().__init__(f"Bild nicht gefunden: {image_id!s}")
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
        super().__init__(f"Reparatur existiert bereits für Fahrzeug {vehicle_id!r}: {folder_name!r}")
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
