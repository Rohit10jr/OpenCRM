"""Frappe platform doctypes.

Phase 0 lands **only** ``User``, because ``AUTH_USER_MODEL`` has to be fixed before the
first migration and every ``owner`` / ``modified_by`` / ``_assign`` value is a User PK
(PHASE_0_FOUNDATION.md section 7). The rest of PHASE_1_MODELS.md cluster 1 - Contact,
ToDo, Communication, Comment, Email Template, File, Tag, Email Account - is phase 1's
and belongs in this same app.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

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


class User(AbstractBaseUser, PermissionsMixin):
    """Frappe ``User``. The PK is the email address, not an integer.

    53 source references assume this: ``owner``, ``modified_by``, ``_assign`` entries,
    ``ToDo.allocated_to`` and every ``@me`` filter resolve to this value. The one
    exception is the built-in ``Administrator``, whose PK is the literal string
    ``"Administrator"`` - which is why this is a CharField and not an EmailField.
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
