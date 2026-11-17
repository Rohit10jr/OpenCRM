"""Test-only export metadata."""


def placeholder_export_field_info(fields: list[str]) -> list[dict]:
    """Return intentionally incomplete descriptors for generic export tests."""

    return [
        {"fieldname": field, "label": field, "fieldtype": "Data"}
        for field in fields
    ]


placeholder_export_field_info.test_only_export_placeholder = True
