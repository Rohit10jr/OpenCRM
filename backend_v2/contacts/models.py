"""CONTACTS' documents (specs/CONTACTS.md section 3).

Milestone 1: the reference data. Salutation and Gender
(`backend/frappe_platform/models.py:1842-1870`) and CRM Industry
(`backend/crm_app/models/taxonomy.py:83-91`), each named by its one field.
"""

from django.db import models

from core.models import BaseDocument
from core.naming import FieldValue


class Salutation(BaseDocument):
    """The Link target of `salutation` on a contact, a lead and a deal (FINDINGS 66)."""

    DOCTYPE = "Salutation"
    NAME_STRATEGY = FieldValue("salutation", label="Salutation")

    salutation = models.CharField("Salutation", max_length=140, unique=True)

    class Meta(BaseDocument.Meta):
        ordering = ["name"]


class Gender(BaseDocument):
    """The Link target of `gender` on a contact, a lead and a deal (FINDINGS 66)."""

    DOCTYPE = "Gender"
    NAME_STRATEGY = FieldValue("gender", label="Gender")

    gender = models.CharField("Gender", max_length=140, unique=True)

    class Meta(BaseDocument.Meta):
        ordering = ["name"]


class CRMIndustry(BaseDocument):
    """An organization's industry, a vocabulary (reviewed-open)."""

    DOCTYPE = "CRM Industry"
    NAME_STRATEGY = FieldValue("industry", label="Industry")

    industry = models.CharField(max_length=140, blank=True, default="")

    class Meta(BaseDocument.Meta):
        ordering = ["name"]
