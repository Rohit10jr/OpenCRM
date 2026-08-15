"""``BaseDocument`` - the Frappe standard fields every document carries.

PHASE_0_FOUNDATION.md section 3. The frontend reads these directly, so none of them
are optional.
"""

from django.db import models
from django.db.models.base import ModelBase
from django.utils import timezone

from frappe_core import naming as naming_strategies
from frappe_core.session import get_current_user

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

        creating = self._state.adding
        if creating:
            self._assign_name()
            # Frappe validates on insert, after naming, for every name however it was
            # produced - generated, prompt-supplied, or caller-forced (naming.py:181).
            # ``pk`` is still None for autoincrement, which the database assigns.
            if self.pk:
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

        return super().save(*args, **kwargs)


class AutoIncrementDocument(BaseDocument):
    """For the three doctypes whose ``autoname`` really is ``autoincrement``.

    Django permits overriding a field inherited from an abstract base, which is how the
    string ``name`` becomes an integer here.
    """

    name = models.BigAutoField(primary_key=True)

    class Meta(BaseDocument.Meta):
        abstract = True
        name_strategy = naming_strategies.AutoIncrement()
