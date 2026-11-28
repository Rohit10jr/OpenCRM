"""Account models."""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models, transaction
from django.utils import timezone

from core.models import BaseDocument, TreeDocument
from core.naming import Hash

from .authentication import new_token_version
from .roles import ADMINISTRATOR, GUEST, ROLE_ADMINISTRATOR, ROLE_SYSTEM_MANAGER


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
        """Create a Django superuser with the CRM's System Manager authority."""
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("enabled", True)
        user = self.create_user(name, password, **extra)

        from django.contrib.auth.models import Group

        group, _ = Group.objects.get_or_create(name=ROLE_SYSTEM_MANAGER)
        user.groups.add(group)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    """Frappe User, whose primary key is normally its normalized email address."""

    # Not a BaseDocument (Django needs AbstractBaseUser), but a doctype like any other:
    # the old registry gave it one (backend/frappe_core/registry.py:198-205), and the
    # delete check, the cascade and the DocType search look it up by this name.
    DOCTYPE = "User"

    # Declared now; nothing enforces these until field access and email validation land.
    EMAIL_FIELDS = ("email",)
    ATTACH_FIELDS = ("user_image",)
    #: The send-from accounts on the Profile screen (CONFIGURATION's User Email rows):
    #: only System Manager writes them; anyone else's `user_emails` is dropped and the
    #: rest of the save applies (old `frappe_platform/models.py:245-249`). A user gets a
    #: row by an Email Account with their address linking itself.
    PRIVILEGED_WRITE_FIELDS = ("user_emails",)
    PRIVILEGED_WRITE_ROLES = ("System Manager",)

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
    onboarding_status = models.TextField(blank=True, default="")
    language = models.CharField(max_length=20, blank=True, default="")
    email_signature = models.TextField(blank=True, default="")
    reset_password_key = models.CharField(
        max_length=64, blank=True, default="", db_index=True
    )
    last_reset_password_key_generated_on = models.DateTimeField(null=True, blank=True)
    token_version = models.PositiveBigIntegerField(default=new_token_version)
    is_staff = models.BooleanField(default=False)
    creation = models.DateTimeField(default=timezone.now, editable=False)
    modified = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "name"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    SENSITIVE_FIELDS = (
        "groups",
        "user_permissions",
        "is_superuser",
        "is_staff",
        "reset_password_key",
        "last_reset_password_key_generated_on",
        "token_version",
    )
    READONLY_FIELDS = ("enabled", "user_type")

    BUILTIN_NAMES = frozenset({ADMINISTRATOR, GUEST})

    class Meta:
        verbose_name = "User"

    def __str__(self) -> str:
        return str(self.name)

    def save(self, *args, user=None, **kwargs):
        # The resource recipe passes the actor (`save(user=...)`); `User` keeps no
        # owner/modified_by stamps (specs/ACCOUNTS.md section 4.1), so it is ignored.
        del user
        if self._state.adding:
            # As BaseDocument does: a create never turns into an update of a row whose
            # name differs only by case once lowercased below.
            kwargs.setdefault("force_insert", True)
        if not self.full_name:
            self.full_name = " ".join(
                part for part in (self.first_name, self.last_name) if part
            )

        if self.name and str(self.name) not in self.BUILTIN_NAMES:
            self.name = str(self.name).strip().lower()
            if self.email:
                self.email = str(self.email).strip().lower()

        super().save(*args, **kwargs)

        # Upstream logs the user out on every save while disabled. Revoking tokens on
        # every such save also keeps them stale if the account is later re-enabled.
        if not self.enabled:
            from .authentication import bump_token_version

            bump_token_version(self)

    @property
    def is_active(self) -> bool:
        return self.enabled

    def get_roles(self) -> set[str]:
        if not hasattr(self, "_roles_cache"):
            roles = set(self.groups.values_list("name", flat=True))
            if self.name == ADMINISTRATOR:
                roles.add(ROLE_ADMINISTRATOR)
            self._roles_cache = roles
        return set(self._roles_cache)

    def clear_roles_cache(self) -> None:
        self.__dict__.pop("_roles_cache", None)

    def refresh_from_db(self, *args, **kwargs):
        self.clear_roles_cache()
        return super().refresh_from_db(*args, **kwargs)

    def has_role(self, role: str) -> bool:
        return role in self.get_roles()


INVITATION_ROLE_CHOICES = [
    ("", ""),
    ("Sales User", "Sales User"),
    ("Sales Manager", "Sales Manager"),
    ("System Manager", "System Manager"),
]
INVITATION_STATUS_CHOICES = [
    ("", ""),
    ("Pending", "Pending"),
    ("Accepted", "Accepted"),
    ("Expired", "Expired"),
]


class CRMInvitation(BaseDocument):
    """An invitation to join with a role (old `crm_app/models/metadata.py`).

    `key` is a bearer token: whoever holds it redeems the invitation and its role. It is
    minted by `invite_by_email`, and by the resource's create, which only System Manager
    or Administrator may call (PE-8); accepting refuses an empty key
    (specs/ACCOUNTS.md section 4.6).
    """

    DOCTYPE = "CRM Invitation"
    NAME_STRATEGY = Hash()
    SENSITIVE_FIELDS = ("key",)
    #: Set by the server (PE-8): never written through the resource.
    READONLY_FIELDS = ("invited_by", "status", "email_sent_at", "accepted_at")

    email = models.CharField(max_length=140)
    role = models.CharField(max_length=40, choices=INVITATION_ROLE_CHOICES)
    key = models.CharField(max_length=140, blank=True, default="", db_index=True)
    invited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_invitations",
    )
    status = models.CharField(
        max_length=20, choices=INVITATION_STATUS_CHOICES, blank=True, default=""
    )
    email_sent_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseDocument.Meta):
        ordering = ["-creation"]

    def save(self, *args, **kwargs):
        creating = self._state.adding
        result = super().save(*args, **kwargs)
        if creating:
            # Any creation sends, as the old post_save did (async_signals.py:208-218):
            # invite_by_email and a manager's direct resource create alike. A direct call
            # here, not a signal (REBUILD_PLAN §5); after commit, so the worker finds the
            # row (A-22).
            from accounts.tasks import send_invitation_email

            name = str(self.pk)
            transaction.on_commit(lambda: send_invitation_email.delay(name))
        return result


class CRMSalesHierarchy(TreeDocument):
    """The org chart the sales row rules walk (old `crm_app/models/metadata.py:257-290`)."""

    DOCTYPE = "CRM Sales Hierarchy"
    NAME_STRATEGY = Hash()
    PARENT_FIELD = "reports_to"
    FETCH_FROM = {"full_name": ("user", "full_name")}

    full_name = models.CharField(max_length=280, blank=True, default="")
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="hierarchy_nodes",
        db_index=True,
    )
    reports_to = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="reports"
    )
    old_parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    is_group = models.BooleanField(default=False)

    class Meta(TreeDocument.Meta):
        ordering = ["lft"]
