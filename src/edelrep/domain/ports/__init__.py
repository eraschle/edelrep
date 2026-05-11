from edelrep.domain.ports.email_inbox import EmailAttachment, EmailInbox, EmailMessage
from edelrep.domain.ports.fuzzy_matcher import FuzzyMatcher
from edelrep.domain.ports.image_repository import ImageRepository
from edelrep.domain.ports.repair_repository import RepairRepository
from edelrep.domain.ports.search_index import SearchIndex
from edelrep.domain.ports.storage_backend import StorageBackend
from edelrep.domain.ports.vehicle_repository import VehicleRepository

__all__ = [
    "EmailAttachment",
    "EmailInbox",
    "EmailMessage",
    "FuzzyMatcher",
    "ImageRepository",
    "RepairRepository",
    "SearchIndex",
    "StorageBackend",
    "VehicleRepository",
]
