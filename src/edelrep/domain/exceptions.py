class DomainError(Exception):
    """Base class for all domain-level errors."""


class InvalidVehicleId(DomainError):
    """Raised when a registration number does not match the allowed pattern."""

    def __init__(self, value: str) -> None:
        super().__init__(f"Invalid vehicle registration number: {value!r}")
        self.value = value
