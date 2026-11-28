"""Invitations: `crm.api.invite_by_email` and `crm.api.accept_invitation`.

Ported from `backend/crm_app/api/misc.py:75-123` and `auth_pages.py:308-438`, messages
verbatim (specs/ACCOUNTS.md section 4.6). The key comes from the email, never from the
API: it is minted here and nowhere else.
"""

from __future__ import annotations

import re
import secrets

from django.contrib.auth.models import Group
from django.utils import timezone

from accounts import password_reset
from accounts.models import CRMInvitation, User
from accounts.services import issue_tokens
from accounts.user_roles import only_for
from core.exceptions import PermissionError, ValidationError

_EMAIL_SPLIT = re.compile(r"[,\n;]+")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
INVITABLE_ROLES = ["System Manager", "Sales Manager", "Sales User"]
INVALID_KEY = "Invalid or expired key"

#: The named role plus the ones it implies (upstream `crm_invitation.py:66-72`).
IMPLIED_ROLES = {
    "System Manager": ("Sales Manager", "Sales User"),
    "Sales Manager": ("Sales User",),
    "Sales User": (),
}


def new_invitation_key() -> str:
    """The one key generator for both ways an invitation is made."""
    return secrets.token_hex(20)


def split_emails(value: str) -> list[str]:
    return [e.strip() for e in _EMAIL_SPLIT.split(value or "") if e.strip()]


def invite_by_email(user, emails: str, role: str):
    """Answers who was already a member, who already had an invitation of any status,
    and who was invited; `None` for an empty or wholly invalid list, after the checks."""
    only_for(["Sales Manager", "System Manager"], user)
    user_roles = user.get_roles()
    if role == "System Manager" and "System Manager" not in user_roles:
        raise PermissionError("You are not allowed to invite System Managers")
    if role == "Sales Manager" and "System Manager" not in user_roles:
        raise PermissionError("You are not allowed to invite Sales Managers")
    if role not in INVITABLE_ROLES:
        raise PermissionError("Cannot invite for this role")

    if not emails:
        return None
    email_list = [e for e in split_emails(emails) if _EMAIL_RE.match(e)]
    if not email_list:
        return None

    existing_members = list(
        User._default_manager.filter(email__in=email_list).values_list("email", flat=True)
    )
    # Any status: an expired or accepted invitation still blocks a re-invite.
    existing_invites = list(
        CRMInvitation._default_manager.filter(
            email__in=email_list, role__in=INVITABLE_ROLES
        ).values_list("email", flat=True)
    )
    # From a set, as the old code: the order is not stable (the body diff compares a set).
    to_invite = list(set(email_list) - set(existing_members) - set(existing_invites))
    for email in to_invite:
        # PE-8: `invited_by` as upstream's before_insert sets it on every insert.
        CRMInvitation(
            email=email,
            role=role,
            status="Pending",
            key=new_invitation_key(),
            invited_by=user,
        ).save(user=user)

    return {
        "existing_members": existing_members,
        "existing_invites": existing_invites,
        "to_invite": to_invite,
    }


def accept_invitation(key: str) -> dict:
    """Redeem an invitation. A new user gets a set-password link (an ordinary one-hour
    reset key); an existing one is logged in."""
    if not key:
        raise ValidationError(INVALID_KEY)
    invitation = CRMInvitation._default_manager.filter(key=key).first()
    if invitation is None:
        raise ValidationError(INVALID_KEY)

    is_new_user = _accept(invitation)
    account = User._default_manager.filter(
        pk=str(invitation.email).strip().lower()
    ).first()
    if is_new_user:
        raw_key = password_reset.issue_key(account)
        return {"status": "set_password", "redirect_to": password_reset.reset_link(raw_key)}
    return {"status": "logged_in", "redirect_to": "/crm", **issue_tokens(account)}


def _accept(invitation) -> bool:
    if invitation.status != "Pending":
        raise ValidationError(INVALID_KEY)
    # Claim it atomically: only a row still Pending with this key is updated, so of two
    # racing requests one wins and the key dies with it.
    claimed = CRMInvitation._default_manager.filter(
        pk=invitation.pk, status="Pending", key=invitation.key
    ).update(status="Accepted", accepted_at=timezone.now(), key="")
    if not claimed:
        raise ValidationError(INVALID_KEY)
    account, is_new_user = _create_user_if_not_exists(invitation.email)
    for name in (invitation.role, *IMPLIED_ROLES.get(invitation.role, ())):
        group, _ = Group.objects.get_or_create(name=name)
        account.groups.add(group)
    return is_new_user


def _create_user_if_not_exists(email: str):
    """Enabled, with no usable password until the reset key mints one."""
    address = str(email).strip().lower()
    existing = User._default_manager.filter(pk=address).first()
    if existing is not None:
        return existing, False
    first_name = address.split("@")[0].title()
    account = User(
        name=address, email=address, first_name=first_name, full_name=first_name, enabled=True
    )
    account.set_unusable_password()
    account.save()
    return account, True
