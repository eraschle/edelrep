import re

import pytest
from hypothesis import given, strategies as st

from edelrep.domain.exceptions import InvalidVehicleId
from edelrep.domain.value_objects import VehicleId

VALID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def test_accepts_simple_numeric_registration() -> None:
    vid = VehicleId("12345")
    assert vid.registration_number == "12345"


def test_accepts_max_length() -> None:
    value = "a" * 64
    assert VehicleId(value).registration_number == value


@pytest.mark.parametrize(
    "bad_value",
    ["", "a" * 65, "with space", "umlaut-ü", "slash/here", "123!", "tab\there"],
)
def test_rejects_invalid_strings(bad_value: str) -> None:
    with pytest.raises(InvalidVehicleId) as info:
        VehicleId(bad_value)
    assert info.value.value == bad_value


def test_is_frozen() -> None:
    vid = VehicleId("12345")
    with pytest.raises(AttributeError):
        vid.registration_number = "67890"  # type: ignore[misc]


def test_is_hashable_and_equal_by_value() -> None:
    a = VehicleId("12345")
    b = VehicleId("12345")
    assert a == b
    assert hash(a) == hash(b)
    assert {a, b} == {a}


@given(st.from_regex(VALID_PATTERN, fullmatch=True))
def test_property_valid_inputs_round_trip(value: str) -> None:
    assert VehicleId(value).registration_number == value


@given(st.text(min_size=0, max_size=80))
def test_property_only_pattern_matches_succeed(value: str) -> None:
    if VALID_PATTERN.fullmatch(value):
        VehicleId(value)
    else:
        with pytest.raises(InvalidVehicleId):
            VehicleId(value)
