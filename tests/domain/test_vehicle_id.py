import re

import pytest
from hypothesis import given, strategies as st

from edelrep.domain.exceptions import InvalidRegistrationNumber, InvalidVin
from edelrep.domain.value_objects import (
    validate_registration_number,
    validate_vin,
)

VALID_REG_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
VALID_VIN_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,32}$")


def test_registration_accepts_simple_numeric() -> None:
    assert validate_registration_number("12345") == "12345"


def test_registration_accepts_max_length() -> None:
    value = "a" * 64
    assert validate_registration_number(value) == value


def test_registration_strips_whitespace() -> None:
    assert validate_registration_number("  CHZH1234  ") == "CHZH1234"


@pytest.mark.parametrize(
    "bad_value",
    ["", "a" * 65, "with space", "umlaut-ü", "slash/here", "123!", "tab\there"],
)
def test_registration_rejects_invalid_strings(bad_value: str) -> None:
    with pytest.raises(InvalidRegistrationNumber) as info:
        validate_registration_number(bad_value)
    assert info.value.value == bad_value


def test_vin_normalises_to_upper() -> None:
    assert validate_vin("wdb12345") == "WDB12345"


@pytest.mark.parametrize(
    "bad_value",
    ["", "a" * 33, "with space", "ü-vin", "slash/", "vin!"],
)
def test_vin_rejects_invalid_strings(bad_value: str) -> None:
    with pytest.raises(InvalidVin) as info:
        validate_vin(bad_value)
    assert info.value.value == bad_value


@given(st.from_regex(VALID_REG_PATTERN, fullmatch=True))
def test_property_registration_round_trip(value: str) -> None:
    # validate strips, so compare against stripped form
    assert validate_registration_number(value) == value.strip()


@given(st.text(min_size=0, max_size=80))
def test_property_registration_pattern_match(value: str) -> None:
    stripped = value.strip()
    if VALID_REG_PATTERN.fullmatch(stripped):
        validate_registration_number(value)
    else:
        with pytest.raises(InvalidRegistrationNumber):
            validate_registration_number(value)
