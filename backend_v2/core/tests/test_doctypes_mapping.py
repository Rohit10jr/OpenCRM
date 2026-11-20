"""`declared_doctypes()` is cached for the process, so its answer is read-only."""

import pytest

from core.doctypes import declared_doctypes, model_for_doctype


def test_the_declared_doctypes_cannot_be_changed_by_a_caller():
    doctypes = declared_doctypes()
    with pytest.raises(TypeError):
        doctypes["User"] = object
    with pytest.raises(TypeError):
        del doctypes["User"]
    with pytest.raises(AttributeError):
        doctypes.pop("User")
    assert model_for_doctype("User") is doctypes["User"]


def test_it_still_reads_as_a_mapping():
    doctypes = declared_doctypes()
    assert "User" in doctypes
    assert dict(doctypes.items())["User"] is doctypes.get("User")
    assert sorted(doctypes) == sorted(doctypes.keys())
