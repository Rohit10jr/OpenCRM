"""Standard fields and lifecycle shared by document models."""

import json
import re
import zlib
from email.utils import parseaddr
from html import escape

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, connection, models, transaction
from django.db.models import Q, Subquery
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from core import naming
from core.exceptions import InvalidEmailAddressError, NestedSetRecursionError
from core.translate import _


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
                _("{0} is not a valid Email Address").format(escape(candidate))
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
    POLYMORPHIC_CHILD_TABLES = {}
    DYNAMIC_LINK_FIELDS = ()
    TRACKED_FIELDS = ()

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

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        if cls.TRACKED_FIELDS:
            from core.versions import capture_tracked_values

            instance._tracked_snapshot = capture_tracked_values(instance)
        return instance

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
        result = super().save(*args, **kwargs)

        if self.TRACKED_FIELDS:
            from core.versions import capture_tracked_values, record_version

            before = None if creating else getattr(self, "_tracked_snapshot", None)
            record_version(self, before, user)
            self._tracked_snapshot = capture_tracked_values(self)

        return result


class Version(BaseDocument):
    """A withheld field-change audit row."""

    DOCTYPE = "Version"
    NAME_STRATEGY = naming.Hash(10)
    DYNAMIC_LINK_FIELDS = (("ref_doctype", "docname"),)

    ref_doctype = models.CharField(max_length=140, db_index=True)
    docname = models.CharField(max_length=140, db_index=True)
    data = models.TextField(blank=True, default="{}")

    class Meta(BaseDocument.Meta):
        ordering = ["creation"]
        indexes = [
            models.Index(fields=["ref_doctype", "docname"], name="version_ref_idx"),
        ]

    def changes(self) -> list[list]:
        try:
            return json.loads(self.data or "{}").get("changed", [])
        except (TypeError, ValueError):
            return []


class SingletonDocument(BaseDocument):
    """A settings document whose one row is named after its document type."""

    IS_SINGLE = True

    class Meta(BaseDocument.Meta):
        abstract = True

    @classmethod
    def singleton_name(cls) -> str:
        return cls.DOCTYPE or cls.__name__

    @classmethod
    def load(cls, *, user):
        document = cls._default_manager.filter(pk=cls.singleton_name()).first()
        if document is not None:
            return document
        try:
            with transaction.atomic():
                document = cls(name=cls.singleton_name())
                document.save(user=user)
                return document
        except IntegrityError:
            return cls._default_manager.get(pk=cls.singleton_name())

    def _assign_name(self):
        if not self.pk:
            self.pk = self.singleton_name()


class AutoIncrementDocument(BaseDocument):
    NAME_STRATEGY = naming.AutoIncrement()
    name = models.BigAutoField(primary_key=True)

    class Meta(BaseDocument.Meta):
        abstract = True


class TreeDocument(BaseDocument):
    """Frappe-compatible nested-set document rebuilt after every ordinary write."""

    PARENT_FIELD = None

    lft = models.IntegerField(null=True, blank=True, db_index=True)
    rgt = models.IntegerField(null=True, blank=True, db_index=True)

    class Meta(BaseDocument.Meta):
        abstract = True

    @classmethod
    def _parent_attname(cls):
        if not cls.PARENT_FIELD:
            raise TypeError(
                _("{0}.PARENT_FIELD must name its parent link").format(cls.__name__)
            )
        return cls._meta.get_field(cls.PARENT_FIELD).attname

    @classmethod
    def _lock_key(cls):
        # Stable across processes, unlike Python's hash(). Keep it in signed int32 range.
        return zlib.crc32(cls._meta.label_lower.encode("utf-8")) & 0x7FFFFFFF

    @classmethod
    def rebuild_tree(cls):
        """Rebuild all bounds under a transaction-scoped lock taken before the read."""
        with transaction.atomic():
            cls._acquire_tree_lock()
            cls._rebuild_locked()

    @classmethod
    def _acquire_tree_lock(cls):
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [cls._lock_key()])

    def _validate_parent_loop(self, parent_name):
        if parent_name == self.pk:
            raise NestedSetRecursionError(
                _("Item cannot be added to its own descendants")
            )
        parent_bounds = type(self)._default_manager.filter(pk=parent_name).values(
            "lft", "rgt"
        ).first()
        if (
            parent_bounds is None
            or parent_bounds["lft"] is None
            or parent_bounds["rgt"] is None
        ):
            return
        ancestors = type(self)._default_manager.filter(
            lft__lte=parent_bounds["lft"],
            rgt__gte=parent_bounds["rgt"],
        ).values_list("pk", flat=True)
        if self.pk in ancestors:
            raise NestedSetRecursionError(
                _("Item cannot be added to its own descendants")
            )

    def save(self, *args, user, **kwargs):
        cls = type(self)
        parent_attname = cls._parent_attname()
        with transaction.atomic():
            cls._acquire_tree_lock()
            parent_name = getattr(self, parent_attname)
            old_parent = None
            if not self._state.adding:
                old_parent = cls._default_manager.filter(pk=self.pk).values_list(
                    parent_attname, flat=True
                ).first()
            if parent_name and (self._state.adding or parent_name != old_parent):
                self._validate_parent_loop(parent_name)
            result = super().save(*args, user=user, **kwargs)
            cls._rebuild_locked()
            return result

    def delete(self, *args, **kwargs):
        cls = type(self)
        with transaction.atomic():
            cls._acquire_tree_lock()
            return super().delete(*args, **kwargs)

    @classmethod
    def _rebuild_locked(cls):
        nodes = list(cls._default_manager.order_by("name"))
        if not nodes:
            return

        children = {}
        by_pk = {node.pk: node for node in nodes}
        for node in nodes:
            parent = getattr(node, cls._parent_attname())
            if parent not in by_pk or parent == node.pk:
                parent = None
            children.setdefault(parent, []).append(node)

        counter = 0
        updated = []

        def visit(node, depth=0):
            nonlocal counter
            if depth > len(nodes):
                return
            counter += 1
            node.lft = counter
            for child in children.get(node.pk, []):
                visit(child, depth + 1)
            counter += 1
            node.rgt = counter
            updated.append(node)

        for root in children.get(None, []):
            visit(root)
        if updated:
            cls._default_manager.bulk_update(updated, ["lft", "rgt"])

    @classmethod
    def tree_q(cls, path, value, inclusive, ancestors):
        """Return a Q on a model linking through ``path`` to this tree."""
        node = cls._default_manager.filter(pk=value).first()
        if node is None or node.lft is None or node.rgt is None:
            return Q(pk__in=[])
        if ancestors:
            bounds = (
                {"lft__lte": node.lft, "rgt__gte": node.rgt}
                if inclusive
                else {"lft__lt": node.lft, "rgt__gt": node.rgt}
            )
        else:
            bounds = (
                {"lft__gte": node.lft, "rgt__lte": node.rgt}
                if inclusive
                else {"lft__gt": node.lft, "rgt__lt": node.rgt}
            )
        related = cls._default_manager.filter(**bounds).order_by().values("pk")
        return Q(**{f"{path}__in": Subquery(related)})

def _is_tree_model(sender):
    return (
        isinstance(sender, type)
        and issubclass(sender, TreeDocument)
        and not sender._meta.abstract
    )


# FINDINGS 96: backend/ shares the delete-then-lock pattern; lock the tree first.
@receiver(pre_delete, dispatch_uid="core.tree_document.lock_before_delete")
def _lock_tree_before_delete(sender, **kwargs):
    if _is_tree_model(sender):
        sender._acquire_tree_lock()


@receiver(post_delete, dispatch_uid="core.tree_document.delete")
def _rebuild_tree_after_delete(sender, **kwargs):
    if _is_tree_model(sender):
        sender.rebuild_tree()
