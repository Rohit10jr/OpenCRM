"""Frappe platform doctypes - PHASE_1_MODELS.md cluster 1.

These ship **no JSON in the CRM repo** - they belong to the Frappe framework, which is
not vendored here. So unlike the 39 CRM doctypes, their field lists are reconstructed
from how the CRM *uses* them, and each model below cites the usage that justifies it.

Per PHASE_1_MODELS.md section 1: "Port only the fields the CRM actually uses - do not
reimplement Frappe's full platform."

**Naming strategies here are the weakest evidence in the port.** The CRM source shows
which fields exist but never the ``autoname`` of a platform doctype. Each choice below
carries a confidence note; the set is flagged in PROGRESS.md for review.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.utils import timezone

from frappe_core.assignment import register_todo_model
from frappe_core.models import BaseDocument
from frappe_core.naming import FieldValue, Hash, Prompt
from frappe_core.registry import register_doctype

#: The four roles seeded as Django Groups. PHASE_2_PERMISSIONS.md section 5.
ROLE_ADMINISTRATOR = "Administrator"
ROLE_SYSTEM_MANAGER = "System Manager"
ROLE_SALES_MANAGER = "Sales Manager"
ROLE_SALES_USER = "Sales User"

SEEDED_ROLES = (
    ROLE_ADMINISTRATOR,
    ROLE_SYSTEM_MANAGER,
    ROLE_SALES_MANAGER,
    ROLE_SALES_USER,
)

#: Frappe's two built-in users. ``Administrator`` bypasses every permission check as a
#: *user*, independently of its role (PHASE_2_PERMISSIONS.md section 5).
ADMINISTRATOR = "Administrator"
GUEST = "Guest"


class UserManager(BaseUserManager):
    def create_user(self, name, password=None, **extra):
        if not name:
            raise ValueError("User requires a name (the email address)")
        extra.setdefault("email", name if "@" in str(name) else "")
        user = self.model(name=name, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, name, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("enabled", True)
        return self.create_user(name, password, **extra)


@register_doctype("User")
class User(AbstractBaseUser, PermissionsMixin):
    """Frappe ``User``. The PK is the email address, not an integer.

    53 source references assume this: ``owner``, ``modified_by``, ``_assign`` entries,
    ``ToDo.allocated_to`` and every ``@me`` filter resolve to this value. The one
    exception is the built-in ``Administrator``, whose PK is the literal string
    ``"Administrator"`` - which is why this is a CharField and not an EmailField.

    Deliberately **not** a ``BaseDocument``: Django requires ``AUTH_USER_MODEL`` to
    derive from ``AbstractBaseUser``, and a user has no ``owner``/``_assign`` of its own.
    """

    name = models.CharField(max_length=140, primary_key=True)
    email = models.EmailField(max_length=140, blank=True, default="")
    first_name = models.CharField(max_length=140, blank=True, default="")
    last_name = models.CharField(max_length=140, blank=True, default="")
    full_name = models.CharField(max_length=280, blank=True, default="")
    user_image = models.CharField(max_length=500, blank=True, default="")
    enabled = models.BooleanField(default=True)
    user_type = models.CharField(max_length=50, default="System User")
    time_zone = models.CharField(max_length=100, blank=True, default="")
    mobile_no = models.CharField(max_length=140, blank=True, default="")
    phone = models.CharField(max_length=140, blank=True, default="")

    # Django admin plumbing.
    is_staff = models.BooleanField(default=False)

    creation = models.DateTimeField(default=timezone.now, editable=False)
    modified = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "name"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        db_table = "tabUser"
        verbose_name = "User"

    def __str__(self) -> str:
        return str(self.name)

    def save(self, *args, **kwargs):
        if not self.full_name:
            self.full_name = " ".join(p for p in (self.first_name, self.last_name) if p)
        return super().save(*args, **kwargs)

    @property
    def is_active(self) -> bool:
        """Django's gate for authentication; Frappe calls the same flag ``enabled``."""
        return self.enabled

    def get_roles(self) -> set[str]:
        """The Django equivalent of ``frappe.get_roles(user)``.

        The literal ``Administrator`` user always carries the Administrator role, which
        is how Frappe behaves regardless of what is stored against it.
        """
        roles = set(self.groups.values_list("name", flat=True))
        if self.name == ADMINISTRATOR:
            roles.add(ROLE_ADMINISTRATOR)
        return roles

    def has_role(self, role: str) -> bool:
        return role in self.get_roles()

    @staticmethod
    def default_list_data():
        return {
            "columns": [
                {"label": "Name", "type": "Data", "key": "full_name", "width": "17rem"},
                {"label": "Email", "type": "Data", "key": "name", "width": "12rem"},
                {"label": "Enabled", "type": "Check", "key": "enabled", "width": "6rem"},
            ],
            "rows": ["name", "full_name", "first_name", "user_image", "enabled"],
        }


@register_doctype("Contact")
class Contact(BaseDocument):
    """Frappe ``Contact``, overridden upstream by ``crm/overrides/contact.py``.

    Field set from that override's ``default_list_data`` (``full_name``, ``email_id``,
    ``mobile_no``, ``company_name``, ``image``) plus ``crm/api/contact.py``, which
    appends to ``email_ids`` and ``phone_nos`` and reads ``doc.email_id`` /
    ``doc.mobile_no``, and ``crm/demo/users.py:78``, which filters on ``user``.

    ``email_id`` / ``mobile_no`` / ``phone`` are **denormalised from the child tables** -
    upstream recomputes them on validate from whichever row is flagged primary. Same
    here, in :meth:`sync_primary_values`.

    > **NAMING - LOW CONFIDENCE.** Frappe names a Contact from its full name, with a
    > numeric suffix on collision, but the exact template is not visible from this repo.
    > Implemented as ``full name`` (+ ``-<company>`` when set), deduplicated with a
    > numeric suffix. Flagged in PROGRESS.md; the frontend routes on this value
    > (``/contacts/:contactId``), so confirm before shipping data.
    """

    first_name = models.CharField(max_length=140, blank=True, default="")
    middle_name = models.CharField(max_length=140, blank=True, default="")
    last_name = models.CharField(max_length=140, blank=True, default="")
    full_name = models.CharField(max_length=420, blank=True, default="")
    salutation = models.CharField(max_length=140, blank=True, default="")
    company_name = models.CharField(max_length=140, blank=True, default="")
    designation = models.CharField(max_length=140, blank=True, default="")
    gender = models.CharField(max_length=140, blank=True, default="")
    image = models.CharField(max_length=500, blank=True, default="")
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="contacts"
    )
    # Denormalised from the child tables below.
    email_id = models.CharField(max_length=140, blank=True, default="")
    mobile_no = models.CharField(max_length=140, blank=True, default="")
    phone = models.CharField(max_length=140, blank=True, default="")

    class Meta:
        ordering = ["-modified"]

    @staticmethod
    def default_list_data():
        """Verbatim from ``crm/overrides/contact.py``."""
        return {
            "columns": [
                {"label": "Name", "type": "Data", "key": "full_name", "width": "17rem"},
                {"label": "Email", "type": "Data", "key": "email_id", "width": "12rem"},
                {"label": "Phone", "type": "Data", "key": "mobile_no", "width": "12rem"},
                {"label": "Organization", "type": "Data", "key": "company_name", "width": "12rem"},
                {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
            ],
            "rows": [
                "name",
                "full_name",
                "company_name",
                "email_id",
                "mobile_no",
                "modified",
                "image",
            ],
        }

    def build_full_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p.strip() for p in parts if p and p.strip())

    def _assign_name(self) -> bool:
        """Contact naming - see the class docstring's confidence note."""
        if self.pk:
            return False
        base = self.build_full_name() or self.email_id or "Contact"
        if self.company_name:
            base = f"{base}-{self.company_name}"
        candidate = base
        suffix = 1
        while type(self)._default_manager.filter(pk=candidate).exists():
            suffix += 1
            candidate = f"{base}-{suffix}"
        self.pk = candidate
        return True

    def sync_primary_values(self) -> None:
        """Recompute the denormalised primary email/phone from the child rows."""
        if not self.pk:
            return
        primary_email = self.email_ids.filter(is_primary=True).first() or self.email_ids.first()
        self.email_id = primary_email.email_id if primary_email else ""

        primary_mobile = (
            self.phone_nos.filter(is_primary_mobile_no=True).first() or self.phone_nos.first()
        )
        self.mobile_no = primary_mobile.phone if primary_mobile else ""

        primary_phone = self.phone_nos.filter(is_primary_phone=True).first()
        self.phone = primary_phone.phone if primary_phone else ""

    def save(self, *args, **kwargs):
        self.full_name = self.build_full_name()
        return super().save(*args, **kwargs)


@register_doctype("Contact Email", is_child_table=True)
class ContactEmail(BaseDocument):
    """Child of Contact. ``crm/api/contact.py:74`` appends ``{email_id, is_primary}``."""

    parent_contact = models.ForeignKey(
        Contact, on_delete=models.CASCADE, related_name="email_ids"
    )
    parenttype = models.CharField(max_length=140, default="Contact")
    parentfield = models.CharField(max_length=140, default="email_ids")
    email_id = models.CharField(max_length=140)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["idx"]
        name_strategy = Hash()


@register_doctype("Contact Phone", is_child_table=True)
class ContactPhone(BaseDocument):
    """Child of Contact.

    ``crm/api/contact.py:77`` appends ``{phone, is_primary_mobile_no}``;
    ``test_crm_deal.py:451-454`` shows both primary flags in use.
    """

    parent_contact = models.ForeignKey(
        Contact, on_delete=models.CASCADE, related_name="phone_nos"
    )
    parenttype = models.CharField(max_length=140, default="Contact")
    parentfield = models.CharField(max_length=140, default="phone_nos")
    phone = models.CharField(max_length=140)
    is_primary_phone = models.BooleanField(default=False)
    is_primary_mobile_no = models.BooleanField(default=False)

    class Meta:
        ordering = ["idx"]
        name_strategy = Hash()


@register_doctype("ToDo")
class ToDo(BaseDocument):
    """**Assignment lives here**, not in ``_assign``.

    PHASE_0_FOUNDATION.md section 3 and PHASE_2_PERMISSIONS.md section 2. The permission
    engine queries this table directly; ``_assign`` is only a cache of it, kept in sync
    by the signals ``frappe_core.assignment`` registers at the bottom of this module.

    Fields from ``crm/api/doc.py:609-618`` (``allocated_to``, ``reference_type``,
    ``reference_name``, ``status``) and ``frappe.desk.form.assign_to.set_status`` usage
    in ``crm/api/doc.py:597-604``.

    Naming: ``hash`` - a ToDo has no natural key.
    """

    STATUS_CHOICES = [
        ("Open", "Open"),
        ("Closed", "Closed"),
        ("Cancelled", "Cancelled"),
    ]
    PRIORITY_CHOICES = [("High", "High"), ("Medium", "Medium"), ("Low", "Low")]

    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="Open", db_index=True)
    priority = models.CharField(max_length=50, choices=PRIORITY_CHOICES, default="Medium")
    date = models.DateField(null=True, blank=True)
    allocated_to = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True, related_name="todos", db_index=True
    )
    assigned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_todos"
    )
    description = models.TextField(blank=True, default="")
    reference_type = models.CharField(max_length=140, blank=True, default="", db_index=True)
    reference_name = models.CharField(max_length=140, blank=True, default="", db_index=True)

    class Meta:
        ordering = ["-modified"]
        name_strategy = Hash()
        indexes = [
            # Every list request for CRM Lead / CRM Deal runs the assignment subquery
            # (PHASE_2_PERMISSIONS.md section 2), so this composite is load-bearing.
            models.Index(
                fields=["reference_type", "reference_name", "status"],
                name="todo_reference_status_idx",
            ),
        ]


@register_doctype("Communication")
class Communication(BaseDocument):
    """Email/call timeline on leads and deals.

    Fields ranked by reference count in the CRM source: ``status`` (112),
    ``reference_doctype`` (73), ``content`` (52), ``creation`` (50),
    ``reference_name`` (27), ``subject`` (22), ``sent_or_received`` (18),
    ``communication_type`` (16), ``sender`` (15), ``communication_medium`` (12),
    ``recipients`` (9), ``cc``/``bcc`` (2), ``read_by_recipient`` (2).

    ``crm/api/doc.py:645-663`` counts rows where ``communication_type`` is
    ``Communication`` or ``Automated Message``.
    """

    subject = models.TextField(blank=True, default="")
    content = models.TextField(blank=True, default="")
    communication_type = models.CharField(max_length=50, default="Communication", db_index=True)
    communication_medium = models.CharField(max_length=50, blank=True, default="")
    sent_or_received = models.CharField(max_length=50, blank=True, default="")
    sender = models.CharField(max_length=140, blank=True, default="")
    sender_full_name = models.CharField(max_length=280, blank=True, default="")
    recipients = models.TextField(blank=True, default="")
    cc = models.TextField(blank=True, default="")
    bcc = models.TextField(blank=True, default="")
    reference_doctype = models.CharField(max_length=140, blank=True, default="", db_index=True)
    reference_name = models.CharField(max_length=140, blank=True, default="", db_index=True)
    status = models.CharField(max_length=50, blank=True, default="Linked")
    read_by_recipient = models.BooleanField(default=False)
    seen = models.BooleanField(default=False)
    has_attachment = models.BooleanField(default=False)
    communication_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creation"]
        name_strategy = Hash()
        indexes = [
            models.Index(
                fields=["reference_doctype", "reference_name"],
                name="comm_reference_idx",
            ),
        ]


@register_doctype("Comment")
class Comment(BaseDocument):
    """Feeds the ``_comments`` cache and the activity timeline.

    ``crm/api/doc.py:664-667`` counts ``comment_type="Comment"`` rows per document;
    ``crm/demo/utils.py:70-71`` creates them with ``comment_type="Comment"``.
    """

    comment_type = models.CharField(max_length=50, default="Comment", db_index=True)
    comment_email = models.CharField(max_length=140, blank=True, default="")
    comment_by = models.CharField(max_length=280, blank=True, default="")
    subject = models.TextField(blank=True, default="")
    content = models.TextField(blank=True, default="")
    reference_doctype = models.CharField(max_length=140, blank=True, default="", db_index=True)
    reference_name = models.CharField(max_length=140, blank=True, default="", db_index=True)
    published = models.BooleanField(default=False)

    class Meta:
        ordering = ["-creation"]
        name_strategy = Hash()
        indexes = [
            models.Index(
                fields=["reference_doctype", "reference_name"],
                name="comment_reference_idx",
            ),
        ]


@register_doctype("Email Template")
class EmailTemplate(BaseDocument):
    """Overridden upstream by ``crm/overrides/email_template.py``.

    Field set is exactly that override's ``default_list_data`` rows: ``enabled``,
    ``use_html``, ``reference_doctype``, ``subject``, ``response``, ``response_html``.

    Naming: ``prompt`` - the template's name is user-supplied and shown as its title
    (the override lists ``name`` as the "Name" column, separate from ``subject``).
    """

    enabled = models.BooleanField(default=True)
    use_html = models.BooleanField(default=False)
    subject = models.TextField(blank=True, default="")
    response = models.TextField(blank=True, default="")
    response_html = models.TextField(blank=True, default="")
    reference_doctype = models.CharField(max_length=140, blank=True, default="")

    class Meta:
        ordering = ["-modified"]
        name_strategy = Prompt()

    @staticmethod
    def default_list_data():
        """Verbatim from ``crm/overrides/email_template.py``."""
        return {
            "columns": [
                {"label": "Name", "type": "Data", "key": "name", "width": "17rem"},
                {"label": "Subject", "type": "Data", "key": "subject", "width": "12rem"},
                {"label": "Enabled", "type": "Check", "key": "enabled", "width": "6rem"},
                {"label": "Doctype", "type": "Link", "key": "reference_doctype", "width": "12rem"},
                {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
            ],
            "rows": [
                "name",
                "enabled",
                "use_html",
                "reference_doctype",
                "subject",
                "response",
                "response_html",
                "modified",
            ],
        }


@register_doctype("File")
class File(BaseDocument):
    """Attachments.

    ``crm/api/comment.py:118`` attaches files with ``attached_to_doctype`` /
    ``attached_to_name``; ``crm/api/activities.py:128`` reads them back per reference.

    Note ``file_url`` is a URL string, not a Django ``FileField`` - PHASE_1_MODELS.md
    section 2 maps ``Attach`` that way.
    """

    file_name = models.CharField(max_length=280, blank=True, default="")
    file_url = models.CharField(max_length=500, blank=True, default="")
    is_private = models.BooleanField(default=False)
    attached_to_doctype = models.CharField(max_length=140, blank=True, default="", db_index=True)
    attached_to_name = models.CharField(max_length=140, blank=True, default="", db_index=True)
    attached_to_field = models.CharField(max_length=140, blank=True, default="")
    folder = models.CharField(max_length=280, blank=True, default="")
    file_size = models.BigIntegerField(default=0)
    content_hash = models.CharField(max_length=140, blank=True, default="")

    class Meta:
        ordering = ["-creation"]
        name_strategy = Hash()
        indexes = [
            models.Index(
                fields=["attached_to_doctype", "attached_to_name"],
                name="file_attached_to_idx",
            ),
        ]


@register_doctype("Tag")
class Tag(BaseDocument):
    """Feeds the ``_user_tags`` cache. The PK is the tag text itself."""

    class Meta:
        ordering = ["name"]
        name_strategy = Prompt()


@register_doctype("Email Account")
class EmailAccount(BaseDocument):
    """Outbound/inbound email config.

    Fields verbatim from ``crm/api/settings.py:14-29``, which is the only place the CRM
    creates one.

    Naming: ``field:email_account_name`` - Frappe's Email Account is titled by that
    field and the CRM passes it explicitly on create.
    """

    email_account_name = models.CharField(max_length=140)
    email_id = models.CharField(max_length=140, blank=True, default="")
    service = models.CharField(max_length=140, blank=True, default="")
    enable_incoming = models.BooleanField(default=False)
    enable_outgoing = models.BooleanField(default=False)
    default_incoming = models.BooleanField(default=False)
    default_outgoing = models.BooleanField(default=False)
    email_sync_option = models.CharField(max_length=50, blank=True, default="ALL")
    initial_sync_count = models.IntegerField(default=100)
    create_contact = models.BooleanField(default=True)
    track_email_status = models.BooleanField(default=True)
    use_tls = models.BooleanField(default=True)
    use_imap = models.BooleanField(default=True)
    smtp_server = models.CharField(max_length=140, blank=True, default="")
    smtp_port = models.IntegerField(null=True, blank=True)
    email_server = models.CharField(max_length=140, blank=True, default="")
    # Frappe stores this encrypted; phase 7 owns real credential handling.
    password = models.CharField(max_length=280, blank=True, default="")
    no_smtp_authentication = models.BooleanField(default=False)

    #: Never serialised, never selectable. frappe_core.field_security.
    SENSITIVE_FIELDS = ("password",)

    class Meta:
        ordering = ["-modified"]
        name_strategy = FieldValue("email_account_name")


# ``_assign`` <-> ToDo synchronisation. Phase 0 built the mechanism
# (frappe_core/assignment.py); this is the single call that switches it on now that the
# real ToDo model exists.
register_todo_model(ToDo)


# Contact's denormalised email_id / mobile_no / phone follow its child rows. Upstream
# recomputes them on validate; children are written after the parent (they need its PK),
# so a save-time hook would not see them. Signals on the child tables are the faithful
# equivalent.
def _resync_contact(sender, instance, **kwargs):
    contact = instance.parent_contact
    if contact is None:
        return
    contact.sync_primary_values()
    type(contact)._default_manager.filter(pk=contact.pk).update(
        email_id=contact.email_id, mobile_no=contact.mobile_no, phone=contact.phone
    )


for _child in (ContactEmail, ContactPhone):
    post_save.connect(_resync_contact, sender=_child, dispatch_uid=f"contact.sync.{_child.__name__}")
    post_delete.connect(
        _resync_contact, sender=_child, dispatch_uid=f"contact.unsync.{_child.__name__}"
    )
