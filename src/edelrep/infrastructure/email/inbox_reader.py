import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from edelrep.domain.ports import StorageBackend


_SIDECAR_NAME = "_inbox.json"
_INBOX_PREFIX = "_system/inbox/"


@dataclass(frozen=True, slots=True)
class ParkedMessage:
    """A message that couldn't be auto-routed and was parked under _system/inbox/."""

    slot_id: str
    message_id: str
    from_address: str
    subject: str
    received_at: datetime
    status: str
    attachment_keys: tuple[str, ...] = field(default_factory=tuple)


class InboxReader:
    """Read-only walker over the parked-messages inbox."""

    def __init__(self, backend: "StorageBackend") -> None:
        self._backend = backend

    def list_pending(self) -> list[ParkedMessage]:
        """Return all parked messages, newest first."""
        keys = list(self._backend.list_prefix(_INBOX_PREFIX))
        sidecar_keys = [k for k in keys if k.endswith("/" + _SIDECAR_NAME)]
        results: list[ParkedMessage] = []
        for sidecar_key in sidecar_keys:
            slot_id = sidecar_key.removesuffix("/" + _SIDECAR_NAME)
            attachment_keys = tuple(
                k for k in keys if k.startswith(slot_id + "/") and not k.endswith("/" + _SIDECAR_NAME)
            )
            results.append(self._parse_sidecar(slot_id, sidecar_key, attachment_keys))
        results.sort(key=lambda m: m.received_at, reverse=True)
        return results

    def get(self, slot_id: str) -> ParkedMessage:
        sidecar_key = f"{slot_id}/{_SIDECAR_NAME}"
        if not self._backend.exists(sidecar_key):
            raise FileNotFoundError(f"no parked message at {slot_id!r}")
        attachment_keys = tuple(
            k for k in self._backend.list_prefix(slot_id + "/") if not k.endswith("/" + _SIDECAR_NAME)
        )
        return self._parse_sidecar(slot_id, sidecar_key, attachment_keys)

    def _parse_sidecar(
        self,
        slot_id: str,
        sidecar_key: str,
        attachment_keys: tuple[str, ...],
    ) -> ParkedMessage:
        raw = self._backend.read_bytes(sidecar_key)
        data = json.loads(raw)
        return ParkedMessage(
            slot_id=slot_id,
            message_id=data["message_id"],
            from_address=data["from_address"],
            subject=data["subject"],
            received_at=datetime.fromisoformat(data["received_at"]),
            status=data["status"],
            attachment_keys=attachment_keys,
        )
