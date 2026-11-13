"""Standard fields and lifecycle shared by document models."""

import re
from email.utils import parseaddr
from html import escape

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import models
from django.utils import timezone

from core import naming
from core.exceptions import InvalidEmailAddressError


def validate_email_address(email_str: str) -> str:
    addresses = []
    for candidate in re.split(r"[,\n]", (email_str or "").strip()):
        candidate = candidate.strip()
        if not candidate:
            continue
        address = ""
        if "undisclosed-recipient" not in candidate and not (
            " " in candidate and "<" not in candidate
        ):
            address = parseaddr(candidate)[1]
            try:
                validate_email(address)
            except DjangoValidationError:
                address = ""
        if not address:
            raise InvalidEmailAddressError(
                f"{escape(candidate)} is not a valid Email Address"
            )
        addresses.append(address)
    return ", ".join(addresses)


class DocumentManager(models.Manager):
    def create_for_user(self, *, user, **values):
        document = self.model(**values)
        document.save(user=user, force_insert=True)
        return document


class NamingSeriesCounter(models.Model):
    prefix = models.CharField(max_length=140, primary_key=True)
    current = models.BigIntegerField(default=0)

    class Meta:
        verbose_name = "Naming Series Counter"

    def __str__(self):
        return f"{self.prefix}{self.current}"


class BaseDocument(models.Model):
    NAME_STRATEGY = None
    DOCTYPE = None
    IS_CHILD_TABLE = False
    IS_SINGLE = False
    FETCH_FROM = {}
    EMAIL_FIELDS = ()
    TEXT_LINK_FIELDS = {}
    ALLOW_DANGLING_LINK_FIELDS = ()

    name = models.CharField(max_length=140, primary_key=True, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        db_column="owner",
        editable=False,
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        db_column="modified_by",
        editable=False,
    )
    creation = models.DateTimeField(editable=False, null=True, blank=True)
    modified = models.DateTimeField(editable=False, null=True, blank=True, db_index=True)
    idx = models.IntegerField(default=0)
    docstatus = models.SmallIntegerField(default=0)
    _assign = models.JSONField(default=list, blank=True, db_column="_assign")
    _liked_by = models.JSONField(default=list, blank=True, db_column="_liked_by")
    _comments = models.JSONField(default=list, blank=True, db_column="_comments")
    _user_tags = models.CharField(max_length=500, blank=True, default="", db_column="_user_tags")

    objects = DocumentManager()

    class Meta:
        abstract = True
        ordering = ["-modified"]

    def __str__(self):
        return str(self.pk)

    def get_password(self, fieldname: str = "password") -> str:
        from core.field_access import encrypted_fields
        from core.secrets import decrypt

        if fieldname not in encrypted_fields(type(self)):
            raise ValueError(
                f"{fieldname!r} is not an encrypted field on {type(self).__name__}"
            )
        return decrypt(getattr(self, fieldname, ""))

    def apply_fetch_from(self):
        for target, (link_field, source_field) in self.FETCH_FROM.items():
            linked = getattr(self, link_field, None)
            if linked is not None:
                value = getattr(linked, source_field, None)
                setattr(self, target, "" if value is None else value)

    def _validate_email_fields(self):
        for fieldname in self.EMAIL_FIELDS:
            value = getattr(self, fieldname, None)
            if value:
                validate_email_address(str(value))

    def _validate_text_links(self):
        from core.links import validate_text_links

        validate_text_links(self)

    def _assign_name(self):
        strategy = self.NAME_STRATEGY
        if strategy is None or strategy.db_assigned or self.pk:
            return
        generated = strategy.generate(self)
        if generated is not None:
            self.pk = generated

    def save(self, *args, user, **kwargs):
        if user is None or user == "":
            raise TypeError("`user` is required to save a document")

        now = timezone.now()
        user_name = user.pk if isinstance(user, models.Model) else str(user)

        self.apply_fetch_from()
        self._validate_email_fields()
        self._validate_text_links()

        creating = self._state.adding
        if creating:
            self._assign_name()
            if self.pk is not None:
                self.pk = naming.validate_name(
                    self.DOCTYPE or type(self).__name__,
                    str(self.pk),
                    is_single=self.IS_SINGLE,
                )
            if not self.creation:
                self.creation = now
            if self.owner_id is None:
                self.owner_id = user_name
        self.modified = now
        self.modified_by_id = user_name

        if creating:
            kwargs["force_insert"] = True
        return super().save(*args, **kwargs)


class AutoIncrementDocument(BaseDocument):
    NAME_STRATEGY = naming.AutoIncrement()
    name = models.BigAutoField(primary_key=True)

    class Meta(BaseDocument.Meta):
        abstract = True
