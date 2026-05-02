import json
from pathlib import Path

import pytest

from edelrep.domain.exceptions import SidecarSchemaError
from edelrep.infrastructure.filesystem.sidecar import (
    CURRENT_SCHEMA_VERSION,
    read_sidecar,
    write_sidecar,
)


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "_vehicle.json"
    write_sidecar(target, {"foo": "bar", "n": 3})
    data = read_sidecar(target)
    assert data == {"foo": "bar", "n": 3}


def test_write_injects_schema_version(tmp_path: Path) -> None:
    target = tmp_path / "_vehicle.json"
    write_sidecar(target, {"foo": "bar"})
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["schema_version"] == CURRENT_SCHEMA_VERSION
    assert raw["foo"] == "bar"


def test_write_rejects_caller_provided_schema_version(tmp_path: Path) -> None:
    target = tmp_path / "_vehicle.json"
    with pytest.raises(ValueError, match="schema_version"):
        write_sidecar(target, {"schema_version": 99, "foo": "bar"})


def test_read_rejects_unknown_version(tmp_path: Path) -> None:
    target = tmp_path / "_vehicle.json"
    target.write_text(json.dumps({"schema_version": 99, "foo": "bar"}), encoding="utf-8")
    with pytest.raises(SidecarSchemaError) as info:
        read_sidecar(target)
    assert info.value.expected == CURRENT_SCHEMA_VERSION
    assert info.value.actual == 99


def test_read_rejects_missing_version(tmp_path: Path) -> None:
    target = tmp_path / "_vehicle.json"
    target.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
    with pytest.raises(SidecarSchemaError) as info:
        read_sidecar(target)
    assert info.value.actual is None


def test_write_is_atomic(tmp_path: Path) -> None:
    target = tmp_path / "_vehicle.json"
    write_sidecar(target, {"foo": "bar"})
    assert not list(tmp_path.glob("*.tmp.*"))
