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
from frappe_core.naming import FieldValue, Hash, Prompt, append_number_if_name_exists
from frappe_core.registry import register_doctype
from frappe_core.secrets import EncryptedFieldsMixin

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
    #: Phase 3: read by ``crm.api.session.get_users`` (``crm/api/session.py:29``) and
    #: ``crm.api.get_translations`` (``crm/api/__init__.py:14``).
    language = models.CharField(max_length=20, blank=True, default="")
    #: Phase 3: the first source ``crm.api.get_user_signature`` checks
    #: (``crm/api/__init__.py:25-30``).
    email_signature = models.TextField(blank=True, default="")

    # Django admin plumbing.
    is_staff = models.BooleanField(default=False)

    creation = models.DateTimeField(default=timezone.now, editable=False)
    modified = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "name"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    #: Never on the wire. These four **are** the privilege escalation: `groups` is the
    #: role set our permission layer reads through `get_roles()`, and `is_staff` plus
    #: `is_superuser` together open Django admin at /admin/, which bypasses that layer
    #: entirely. A Sales User could set all of them on their own row - the self-only rule
    #: in `crm_app/permissions/platform_docs.py` permits writing your own document, so
    #: that rule alone does not close this.
    #:
    #: Nothing needs them here: the frontend reads roles from `crm.api.session.get_users`,
    #: and roles are changed through `crm_app.api.user.update_user_role`, which checks who
    #: is asking. Internal ORM use is unaffected - this covers the wire only.
    SENSITIVE_FIELDS = ("groups", "user_permissions", "is_superuser", "is_staff")

    #: Readable, never writable through the generic route.
    #:
    #: `enabled` has to stay visible - the Users settings screen has an Enabled column -
    #: but must not be settable by its own subject.
    #:
    #: Note what this does *not* do: a disabled account cannot re-enable itself even
    #: without this, because SimpleJWT rejects its token at authentication
    #: (`is_active` maps to `enabled`), so the request never reaches a serializer - 401,
    #: verified. This is the second layer, not the first. It earns its place because the
    #: first is a single `is_active` check in a library, and because without it a user can
    #: switch their own account off with one PUT, which is a support ticket rather than an
    #: attack but is nobody's intention.
    #:
    #: `user_type` gates nothing in this port yet (it is stored and returned by the
    #: session endpoints, and nothing branches on it). Upstream treats it as privileged -
    #: System User versus Website User - so it is locked here as cheap precaution before
    #: phase 8 gives it meaning, not because it is currently exploitable.
    READONLY_FIELDS = ("enabled", "user_type")

    class Meta:
        db_table = "tabUser"
        verbose_name = "User"

    def __str__(self) -> str:
        return str(self.name)

    #: Frappe's two built-ins are named from ``first_name``, not from an email
    #: (``frappe/core/doctype/user/user.py:152-153``), which is why they are literally
    #: "Administrator" and "Guest" rather than addresses.
    BUILTIN_NAMES = frozenset({"Administrator", "Guest"})

    def save(self, *args, **kwargs):
        if not self.full_name:
            self.full_name = " ".join(p for p in (self.first_name, self.last_name) if p)

        # Port of ``User.autoname`` (frappe/core/doctype/user/user.py:150-156): the PK is
        # the email, **lowercased and stripped**. Without this, "John@Example.com" and
        # "john@example.com" are two different users - and because ``owner``,
        # ``ToDo.allocated_to``, ``_assign`` entries and every ``@me`` filter compare
        # this value as a string, the mismatch surfaces as silently missing rows rather
        # than an error.
        if self.name and str(self.name) not in self.BUILTIN_NAMES:
            self.name = str(self.name).strip().lower()
            if self.email:
                self.email = str(self.email).strip().lower()

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

    **NAMING - RESOLVED** against ``frappe`` ``version-15``, the branch CRM ``main``
    targets. Contact declares no ``autoname``; naming is a controller method
    (``frappe/contacts/doctype/contact/contact.py:54-63``) - a seventh strategy beyond
    the six in ``PHASE_0_FOUNDATION.md`` section 2. See :meth:`_assign_name`.

    The earlier guess was wrong in three ways, all corrected: ``company_name`` is a
    *fallback* rather than a suffix (``contact.py:463-473``), the first collision suffix
    is ``-1`` rather than ``-2``, and an empty name raises instead of falling back to
    the email address.
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
        """Port of ``get_full_name`` (``frappe/contacts/doctype/contact/contact.py:463``).

        ``company_name`` is a **fallback** used only when first/middle/last are all
        empty - it is never a suffix.
        """
        parts = [self.first_name, self.middle_name, self.last_name]
        full_name = " ".join(p.strip() for p in parts if p and p.strip())
        if not full_name and self.company_name:
            full_name = self.company_name
        return full_name

    def name_links_suffix(self) -> str:
        """The ``-<first Dynamic Link>`` fragment upstream appends (contact.py:57-60).

        Upstream iterates ``self.links`` and ``break``s, so only the *first* row counts.

        ``Dynamic Link`` is a platform doctype outside phase 1 cluster 1, so there is
        nothing to read yet and this returns "". Every CRM path that creates a Contact
        (``crm_lead.py:213``, ``crm_deal.py:427``, ``install.py``, ``demo/``) sets
        ``company_name`` but never appends to ``links``, so upstream's suffix does not
        fire for CRM-created contacts either - the two agree today. **When Dynamic Link
        is ported (it is also needed for ``CRM Call Log.links``), implement this method
        and the naming becomes faithful with no other change.**
        """
        return ""

    def _assign_name(self) -> bool:
        """Port of ``Contact.autoname`` (contact.py:54-63).

        Frappe declares no ``autoname`` in ``contact.json``; naming lives in a
        controller method, which is a seventh strategy beyond the six in
        ``PHASE_0_FOUNDATION.md`` section 2. ``crm/overrides/contact.py`` overrides only
        ``default_list_data``, so this algorithm applies unchanged under the CRM app.

        An empty name is deliberately **not** given a fallback: upstream reaches
        ``validate_name`` with "" and raises "No Name Specified for Contact". CRM always
        supplies one (``crm_lead.py:214`` uses ``first_name or lead_name``, and
        ``lead_name`` itself falls back to the email local part), so raising is safe.
        """
        if self.pk:
            return False
        base = self.build_full_name() + self.name_links_suffix()
        self.pk = append_number_if_name_exists(type(self), base)
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


# Unrouted deliberately. `org_hierarchy` grants access to a record when a ToDo row says
# you are assigned to it, so a writable /api/resource/ToDo let any user create that row
# for any document and read it - the permission check then *passes*, on data the caller
# supplied. Nothing calls this route: the frontend assigns through
# `frappe.desk.form.assign_to.add`, which checks write permission on the document first.
# Full reasoning, the upstream comparison and the permission-rule alternative:
# specs/UNROUTED_DOCTYPES.md.
@register_doctype("ToDo", routable=False)
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
class EmailAccount(EncryptedFieldsMixin, BaseDocument):
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
    #: Phase 3: the fallback source for ``crm.api.get_user_signature``
    #: (``crm/api/__init__.py:32-36``).
    add_signature = models.BooleanField(default=False)
    signature = models.TextField(blank=True, default="")
    #: Phase 3: written by ``crm.api.settings.create_email_account``
    #: (``crm/api/settings.py:12-52`` and its ``email_service_config`` table).
    api_key = models.CharField(max_length=280, blank=True, default="")
    api_secret = models.CharField(max_length=280, blank=True, default="")
    frappe_mail_site = models.CharField(max_length=280, blank=True, default="")
    append_to = models.CharField(max_length=140, blank=True, default="")
    domain = models.CharField(max_length=140, blank=True, default="")
    login_id = models.CharField(max_length=140, blank=True, default="")
    login_id_is_different = models.BooleanField(default=False)
    awaiting_password = models.BooleanField(default=False)
    ascii_encode_password = models.BooleanField(default=False)
    use_ssl = models.BooleanField(default=False)
    use_ssl_for_outgoing = models.BooleanField(default=False)
    use_starttls = models.BooleanField(default=False)
    validate_ssl_certificate = models.BooleanField(default=False)
    incoming_port = models.IntegerField(null=True, blank=True)
    always_use_account_email_id_as_sender = models.BooleanField(default=False)

    #: Never serialised, never selectable. frappe_core.field_security.
    #: ``api_secret`` joins ``password``: it is the Frappe Mail credential.
    SENSITIVE_FIELDS = ("password", "api_secret")

    #: Encrypted at rest (``frappe_core.secrets``). The attribute holds **ciphertext**
    #: once saved - read the credential with ``account.get_password("password")``, never
    #: ``account.password``. Upstream keeps these out of the document table entirely, in
    #: the ``__Auth`` table; we keep the column and encrypt its contents, which reaches
    #: the same property with a data-only migration.
    ENCRYPTED_FIELDS = ("password", "api_secret")

    #: Managers only. Upstream needs no equivalent because it withholds the whole record
    #: from anyone below System Manager - and in doing so leaves its own Profile screen's
    #: "send from" picker empty for ordinary users, since that screen carries no role
    #: condition. We keep the picker working, which means the record is readable, which
    #: means the infrastructure on it has to be narrowed instead.
    #:
    #: What stays visible is exactly what that picker reads: ``name``, ``email_id`` and
    #: ``enable_outgoing``. Everything below describes *how* mail is sent, which is a
    #: manager's business and an attacker's reconnaissance.
    RESTRICTED_FIELDS = (
        "smtp_server",
        "smtp_port",
        "email_server",
        "incoming_port",
        "login_id",
        "domain",
        "api_key",
        "frappe_mail_site",
        "signature",
        "no_smtp_authentication",
        "awaiting_password",
    )

    class Meta:
        ordering = ["-modified"]
        name_strategy = FieldValue("email_account_name")


# ``_assign`` <-> ToDo synchronisation. Phase 0 built the mechanism
# (frappe_core/assignment.py); this is the single call that switches it on now that the
# real ToDo model exists.
register_todo_model(ToDo)


@register_doctype("Dynamic Link", is_child_table=True)
class DynamicLink(BaseDocument):
    """Frappe's generic "this document points at that one" child table.

    Phase 3, carried-over item **C5**. Schema from the framework
    (``frappe/core/doctype/dynamic_link/dynamic_link.json``): ``link_doctype`` (Link to
    DocType), ``link_name`` (Dynamic Link), ``link_title`` (Read Only).

    Polymorphic on **both** ends - it is embedded by several doctypes *and* points at
    several - so it carries ``parent``/``parenttype`` rather than a FK, like the three
    CRM child tables in the same position.

    Unblocks two things upstream depends on:

    * ``CRM Call Log.links`` - attaching notes/tasks/leads/deals to a call, which
      ``crm/api/activities.py:get_linked_calls`` reads.
    * ``Contact.links`` - which upstream's ``Contact.autoname`` consults for its
      company suffix.
    """

    parenttype = models.CharField(max_length=140, blank=True, default="", db_index=True)
    parentfield = models.CharField(max_length=140, blank=True, default="")
    parent = models.CharField(max_length=140, blank=True, default="", db_index=True)

    link_doctype = models.CharField(max_length=140, db_index=True)
    link_name = models.CharField(max_length=140, db_index=True)
    link_title = models.CharField(max_length=280, blank=True, default="")

    class Meta:
        ordering = ["idx"]
        name_strategy = Hash()
        indexes = [
            models.Index(fields=["parenttype", "parent"], name="dynamic_link_parent_idx"),
            models.Index(fields=["link_doctype", "link_name"], name="dynamic_link_target_idx"),
        ]


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
