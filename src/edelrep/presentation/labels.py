"""German UI labels per PLAN.md §11.4."""

VEHICLE_FIELDS: dict[str, str] = {
    "registration_number": "Stammnummer",
    "vin": "Rahmennummer",
    "description": "Bezeichnung",
    "created_at": "Angelegt am",
}

REPAIR_FIELDS: dict[str, str] = {
    "description": "Beschreibung",
    "date": "Datum",
    "created_at": "Angelegt am",
}

IMAGE_FIELDS: dict[str, str] = {
    "uploaded_at": "Hochgeladen am",
    "captured_at": "Aufgenommen am",
}

IMAGE_SOURCE: dict[str, str] = {
    "manual": "Manuell",
    "email": "E-Mail",
}
