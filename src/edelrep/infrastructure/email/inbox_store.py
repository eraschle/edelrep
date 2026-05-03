import json
from datetime import datetime

from ulid import ULID

from edelrep.domain.ports import EmailMessage, StorageBackend


class InboxStore:
    """Writes parked email messages under ``_system/inbox/<slot>/``."""

    def __init__(self, backend: StorageBackend) -> None:
        self._backend = backend

    def park(self, message: EmailMessage, *, status: str = "pending") -> str:
        slot = self._slot_key(message.received_at)
        sidecar = {
            "schema_version": 1,
            "message_id": message.message_id,
            "from_address": message.from_address,
            "subject": message.subject,
            "received_at": message.received_at.isoformat(),
            "status": status,
        }
        text = json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n"
        self._backend.write_bytes(f"{slot}/_inbox.json", text.encode("utf-8"))
        for i, att in enumerate(message.attachments, start=1):
            safe_name = (att.filename or f"part{i}.bin").replace("/", "_").replace("\\", "_")
            self._backend.write_bytes(f"{slot}/{i:04d}_{safe_name}", att.content)
        return slot

    @staticmethod
    def _slot_key(received_at: datetime) -> str:
        ts = received_at.strftime("%Y-%m-%dT%H%M%S")
        return f"_system/inbox/{ts}_{ULID()!s}"
