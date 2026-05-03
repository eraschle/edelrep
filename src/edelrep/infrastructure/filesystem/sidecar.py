import json
from pathlib import Path
from typing import Any

from edelrep.domain.exceptions import SidecarSchemaError
from edelrep.domain.ports import StorageBackend
from edelrep.infrastructure.filesystem.atomic_write import write_text_atomic
from edelrep.infrastructure.filesystem.json_codec import DomainJSONEncoder

CURRENT_SCHEMA_VERSION = 1


def write_sidecar(path: Path, data: dict[str, Any]) -> None:
    if "schema_version" in data:
        raise ValueError("caller must not pre-populate schema_version; sidecar writer owns it")
    payload = {"schema_version": CURRENT_SCHEMA_VERSION, **data}
    text = json.dumps(payload, cls=DomainJSONEncoder, indent=2, ensure_ascii=False)
    write_text_atomic(path, text + "\n")


def read_sidecar(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    actual = raw.get("schema_version") if isinstance(raw, dict) else None
    if actual != CURRENT_SCHEMA_VERSION:
        raise SidecarSchemaError(str(path), expected=CURRENT_SCHEMA_VERSION, actual=actual)
    out = dict(raw)
    out.pop("schema_version", None)
    return out


def read_backend_sidecar(backend: StorageBackend, key: str) -> dict[str, Any]:
    raw_bytes = backend.read_bytes(key)
    raw = json.loads(raw_bytes.decode("utf-8"))
    actual = raw.get("schema_version") if isinstance(raw, dict) else None
    if actual != CURRENT_SCHEMA_VERSION:
        raise SidecarSchemaError(key, expected=CURRENT_SCHEMA_VERSION, actual=actual)
    out = dict(raw)
    out.pop("schema_version", None)
    return out


def write_backend_sidecar(backend: StorageBackend, key: str, data: dict[str, Any]) -> None:
    if "schema_version" in data:
        raise ValueError("caller must not pre-populate schema_version")
    payload = {"schema_version": CURRENT_SCHEMA_VERSION, **data}
    text = json.dumps(payload, cls=DomainJSONEncoder, indent=2, ensure_ascii=False)
    backend.write_bytes(key, (text + "\n").encode("utf-8"))
