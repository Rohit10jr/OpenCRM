"""``BaseDocument`` - the Frappe standard fields every document carries.

PHASE_0_FOUNDATION.md section 3. The frontend reads these directly, so none of them
are optional.
"""

import re
from email.utils import parseaddr
from html import escape

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email as _django_validate_email
from django.db import models
from django.db.models.base import ModelBase
from django.utils import timezone

from frappe_core import naming as naming_strategies
from frappe_core.exceptions import InvalidEmailAddressError
from frappe_core.session import get_current_user


def validate_email_address(email_str: str) -> str:
    """``frappe.utils.validate_email_address(email_str, throw=True)`` (utils/__init__.py:
    166-206): every address in a comma- or newline-separated string is checked (the split
    ``frappe.utils.split_emails`` makes; a semicolon is not a separator), an address may
    carry a display name (``Jane <jane@x.test>``), a bare string with a space is not an
    address, and the first bad one throws ``InvalidEmailAddressError`` with the value
    HTML-escaped: "<value> is not a valid Email Address". Returns the addresses found,
    joined with ", ", as upstream does.
    """
    out = []
    for candidate in re.split(r"[,\n]", (email_str or "").strip()):
        candidate = candidate.strip()
        if not candidate:
            continue
        address = ""
        if "undisclosed-recipient" in candidate or (" " in candidate and "<" not in candidate):
            address = ""
        else:
            address = parseaddr(candidate)[1]
            try:
                _django_validate_email(address)
            except DjangoValidationError:
                address = ""
        if not address:
            raise InvalidEmailAddressError(f"{escape(candidate)} is not a valid Email Address")
        out.append(address)
    return ", ".join(out)

#: Attributes we allow inside ``class Meta`` that Django itself does not understand.
#: They are stripped before Django's ``ModelBase`` validates Meta, then re-attached to
#: the model class as ``_doc_meta``.
DOC_META_KEYS = (
    "name_strategy",
    "doctype",
    "is_child_table",
    "is_single",
    "title_field",
)


class DocumentBase(ModelBase):
    """Metaclass that lets ``class Meta`` carry Frappe-specific declarations.

    Django's ``ModelBase`` rejects unknown ``Meta`` attributes, but
    PHASE_0_FOUNDATION.md section 4 specifies the phase-1 declaration as::

        class Meta:
            name_strategy = NamingSeries("CRM-LEAD-.YYYY.-")

    Keeping that syntax matters - it is what five concurrent phase-1 agents will copy -
    so we pop our keys off Meta before Django sees it.
    """

    def __new__(mcs, cls_name, bases, attrs, **kwargs):
        meta = attrs.get("Meta")
        extracted: dict[str, object] = {}
        if meta is not None:
            for key in DOC_META_KEYS:
                if key in vars(meta):
                    extracted[key] = getattr(meta, key)
                    delattr(meta, key)

        cls = super().__new__(mcs, cls_name, bases, attrs, **kwargs)

        # Inherit from the nearest ancestor, then apply this class's own declarations.
        inherited: dict[str, object] = {}
        for base in reversed(cls.__mro__[1:]):
            inherited.update(getattr(base, "_doc_meta", {}) or {})
        inherited.update(extracted)
        cls._doc_meta = inherited
        return cls


class NamingSeriesCounter(models.Model):
    """One row per resolved naming-series prefix, e.g. ``CRM-LEAD-2026-``.

    Frappe keeps the same thing in ``tabSeries``. Incremented under
    ``select_for_update()`` by :func:`frappe_core.naming.next_series_value`.
    """

    prefix = models.CharField(max_length=140, primary_key=True)
    current = models.BigIntegerField(default=0)

    class Meta:
        db_table = "frappe_naming_series"
        verbose_name = "Naming Series Counter"

    def __str__(self) -> str:
        return f"{self.prefix}{self.current}"


class BaseDocument(models.Model, metaclass=DocumentBase):
    """Abstract base for every ported DocType.

    ``name`` is a string PK by default. The three genuinely-autoincrement doctypes
    (``crm_task``, ``crm_view_settings``, ``crm_product_sync_issue``) use
    :class:`AutoIncrementDocument` instead.
    """

    name = models.CharField(max_length=140, primary_key=True, editable=False)

    owner = models.ForeignKey(
        "frappe_platform.User",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        db_column="owner",
        editable=False,
    )
    modified_by = models.ForeignKey(
        "frappe_platform.User",
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
    #: 0 draft / 1 submitted / 2 cancelled. CRM is 0 everywhere; the column exists for
    #: wire compatibility, the submit workflow is deliberately not implemented.
    docstatus = models.SmallIntegerField(default=0)

    # The four denormalised caches. PHASE_0_FOUNDATION.md section 3.
    # _assign's source of truth is ToDo; phase 2 queries ToDo, never this column.
    _assign = models.JSONField(default=list, blank=True, db_column="_assign")
    _liked_by = models.JSONField(default=list, blank=True, db_column="_liked_by")
    _comments = models.JSONField(default=list, blank=True, db_column="_comments")
    _user_tags = models.CharField(
        max_length=500, blank=True, default="", db_column="_user_tags"
    )

    #: Port of Frappe's ``fetch_from`` (``frappe/model/base_document.py:818-890``): a
    #: field whose value is pulled from a linked document on every save.
    #:
    #: ``{target_field: (link_field, source_field_on_the_linked_doc)}``
    #:
    #: Frappe overwrites unconditionally unless the field also sets ``fetch_if_empty``;
    #: none of the seven in this app do, so this always overwrites too. Declared per
    #: model rather than derived, because we have no DocType metadata to read it from.
    FETCH_FROM: dict[str, tuple[str, str]] = {}

    #: Fields whose edits are recorded in the timeline (:mod:`frappe_core.versions`).
    #: Empty means no history is kept - the default, and correct for most doctypes.
    #: Upstream records *every* field; this port records a declared list. See that
    #: module for why.
    TRACKED_FIELDS: tuple[str, ...] = ()

    #: Data fields whose DocType ``options`` is ``Email``. Upstream validates every one
    #: of them on save (``base_document.py:_validate_data_fields``, 936-940), one
    #: address at a time after splitting on commas; declared per model for the same
    #: reason as ``FETCH_FROM``.
    EMAIL_FIELDS: tuple[str, ...] = ()

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        if cls.TRACKED_FIELDS:
            from frappe_core.versions import capture_tracked_values

            # Snapshot here rather than re-reading on save: the row is already in hand,
            # so the history costs no extra query.
            instance._tracked_snapshot = capture_tracked_values(instance)
        return instance

    def _validate_email_fields(self) -> None:
        """``base_document.py:_validate_data_fields`` for the Email-typed columns."""
        for fieldname in self.EMAIL_FIELDS:
            value = getattr(self, fieldname, None)
            if value:
                validate_email_address(str(value))

    def _validate_text_links(self) -> None:
        """``document.py:_validate_links`` for the Links this port keeps as text columns:
        a value that names no document is refused, as upstream refuses it
        (:mod:`frappe_core.links`)."""
        from frappe_core.links import validate_text_links

        validate_text_links(self)

    def apply_fetch_from(self) -> None:
        """Copy each declared ``FETCH_FROM`` value off its linked document."""
        for target, (link_field, source_field) in self.FETCH_FROM.items():
            linked = getattr(self, link_field, None)
            if linked is None:
                continue
            value = getattr(linked, source_field, None)
            setattr(self, target, "" if value is None else value)

    class Meta:
        abstract = True
        ordering = ["-modified"]

    def __str__(self) -> str:
        return str(self.pk)

    # -- naming ------------------------------------------------------------------

    @classmethod
    def get_name_strategy(cls) -> naming_strategies.NameStrategy | None:
        return (cls._doc_meta or {}).get("name_strategy")

    @classmethod
    def get_doctype(cls) -> str | None:
        """The Frappe DocType string, e.g. ``"CRM Lead"``. Set by ``register_doctype``."""
        return (cls._doc_meta or {}).get("doctype")

    @classmethod
    def is_child_table(cls) -> bool:
        return bool((cls._doc_meta or {}).get("is_child_table"))

    @classmethod
    def is_single(cls) -> bool:
        return bool((cls._doc_meta or {}).get("is_single"))

    def _assign_name(self) -> bool:
        """Populate ``self.pk`` from the declared strategy. Returns True if it set one."""
        strategy = self.get_name_strategy()
        if strategy is None or strategy.db_assigned:
            return False
        if self.pk:
            # prompt supplies the name client-side; anything else with a pk already set
            # is a caller-forced name, which Frappe also permits.
            return False
        generated = strategy.generate(self)
        if generated is None:
            return False
        self.pk = generated
        return True

    # -- lifecycle ---------------------------------------------------------------

    def save(self, *args, **kwargs):
        now = timezone.now()
        user_pk = get_current_user()

        self.apply_fetch_from()
        self._validate_email_fields()
        self._validate_text_links()

        creating = self._state.adding
        if creating:
            self._assign_name()
            # Frappe validates on insert, after naming, for every name however it was
            # produced - generated, prompt-supplied, or caller-forced (naming.py:181).
            # ``is not None`` rather than a truth test: an *empty* name must reach
            # validate_name so it raises "No Name Specified", which is upstream's
            # behaviour and the only thing stopping a nameless row. ``None`` means
            # autoincrement, where the database assigns the PK and there is nothing yet.
            if self.pk is not None:
                self.pk = naming_strategies.validate_name(
                    self.get_doctype(), str(self.pk), is_single=self.is_single()
                )
            if not self.creation:
                self.creation = now
            if self.owner_id is None:
                self.owner_id = user_pk
        self.modified = now
        self.modified_by_id = user_pk

        # An instance that did not come from the database is an INSERT, full stop.
        #
        # Django only auto-forces this when the PK has a default, which a CharField PK
        # does not - so without this it runs UPDATE-then-INSERT. That is not merely a
        # wasted query: for a `prompt` doctype, where the *client* supplies the name,
        # POSTing an existing name would silently UPDATE somebody else's document
        # instead of failing. Forcing the insert turns that into the IntegrityError it
        # should be, which the error handler renders as Frappe's DuplicateEntryError.
        if creating and not kwargs.get("update_fields") and not args:
            kwargs.setdefault("force_insert", True)

        result = super().save(*args, **kwargs)

        if self.TRACKED_FIELDS:
            from frappe_core.versions import capture_tracked_values, record_version

            # None on create: the timeline already carries a "created" entry, and
            # upstream's diff against a non-existent prior document is empty too.
            record_version(self, None if creating else getattr(self, "_tracked_snapshot", None))
            # Re-snapshot so a second save in the same request diffs against what was
            # just written, not against the original load.
            self._tracked_snapshot = capture_tracked_values(self)

        return result


class AutoIncrementDocument(BaseDocument):
    """For the three doctypes whose ``autoname`` really is ``autoincrement``.

    Django permits overriding a field inherited from an abstract base, which is how the
    string ``name`` becomes an integer here.
    """

    name = models.BigAutoField(primary_key=True)

    class Meta(BaseDocument.Meta):
        abstract = True
        name_strategy = naming_strategies.AutoIncrement()


# Imported last, not at the top: `versions` subclasses BaseDocument, so the name has to
# exist first. Django only discovers models reachable from a `models` module, and this is
# what puts `Version` in front of the migration autodetector.
from frappe_core.versions import Version  # noqa: E402,F401
