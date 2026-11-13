"""Account models."""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

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

    # Declared now; nothing enforces these until field access and email validation land.
    EMAIL_FIELDS = ("email",)
    ATTACH_FIELDS = ("user_image",)

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
    token_version = models.PositiveIntegerField(default=0)
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

    def save(self, *args, **kwargs):
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
        roles = set(self.groups.values_list("name", flat=True))
        if self.name == ADMINISTRATOR:
            roles.add(ROLE_ADMINISTRATOR)
        return roles

    def has_role(self, role: str) -> bool:
        return role in self.get_roles()
