"""Verify that all German labels from PLAN.md §11.4 are correctly defined."""

from edelrep.presentation.labels import (
    IMAGE_FIELDS,
    IMAGE_SOURCE,
    REPAIR_FIELDS,
    VEHICLE_FIELDS,
)


def test_vehicle_labels_match_plan() -> None:
    assert VEHICLE_FIELDS["registration_number"] == "Stammnummer"
    assert VEHICLE_FIELDS["vin"] == "Rahmennummer"
    assert VEHICLE_FIELDS["description"] == "Bezeichnung"
    assert VEHICLE_FIELDS["created_at"] == "Angelegt am"


def test_repair_labels_match_plan() -> None:
    assert REPAIR_FIELDS["description"] == "Beschreibung"
    assert REPAIR_FIELDS["date"] == "Datum"
    assert REPAIR_FIELDS["created_at"] == "Angelegt am"


def test_image_labels_match_plan() -> None:
    assert IMAGE_FIELDS["uploaded_at"] == "Hochgeladen am"


def test_image_source_labels_match_plan() -> None:
    assert IMAGE_SOURCE["manual"] == "Manuell"
    assert IMAGE_SOURCE["email"] == "E-Mail"
