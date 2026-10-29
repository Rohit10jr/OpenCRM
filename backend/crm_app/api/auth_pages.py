"""The endpoints behind the auth screens — forgot password, set password, accept invite.

Ports `frappe/core/doctype/user/user.py:1044` (`reset_password`), `:828`
(`update_password`), and `crm/api/__init__.py:83` (`accept_invitation`).

**All three are `allow_guest`.** That is rarer here than anywhere else in this port — these
are the only endpoints an unauthenticated stranger on the internet can reach that *write*
something. `RUNBOOK_PHASE_8.md`: each deserves the scrutiny a phase-7 webhook got.

## The dotted paths are upstream's

`crm.api.accept_invitation` has no module segment because upstream defines it in
`crm/api/__init__.py`, and the invitation email already links to it. The two password paths
are Frappe's own, under `frappe.core.doctype.user.user.*`, because that is where a client
built against a Frappe backend would look.
"""

from __future__ import annotations

import logging

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from frappe_core import password_reset
from frappe_core.exceptions import ValidationError, throw
from frappe_core.security import rate_limit
from frappe_core.whitelist import whitelist

logger = logging.getLogger(__name__)

#: `user.py:1053-1064`. **One sentence, whatever happened** — unknown address, disabled
#: account, Administrator, mail failure, unexpected exception. Upstream names the weakness
#: this closes in a comment: CWE-204, username enumeration through differing messages or
#: status codes. Same reasoning as answering 404 rather than 403 for an unrouted doctype.
GENERIC_RESET_RESPONSE = (
    "If this email is registered with us, we have sent password reset instructions to it. "
    "Please check your inbox."
)

#: `user.py:839-840`. Upstream caps it; a multi-megabyte password is a hashing DoS.
MAX_PASSWORD_SIZE = 512


@whitelist(
    "frappe.core.doctype.user.user.reset_password",
    allow_guest=True,
    methods=("POST",),
)
@rate_limit(limit=10, seconds=60 * 60, key="user", normalise=lambda v: str(v or "").strip().lower())
def reset_password(user: str = "", **extra):
    """`user.py:1041-1067` — forgot password.

    **The response never varies.** Every branch below returns the same sentence, and the
    function returns it once at the end rather than in each branch, so a later edit cannot
    accidentally introduce a second answer.

    Rate-limited per hour **per address** as well as per IP (`key="user"`), which upstream
    does not do: its limiter is per IP alone. Without the address in the bucket, one caller
    still cannot spam one victim — but ten addresses per hour per IP is a lower cap than
    ten *requests*, and mail sent to a stranger is the cost being limited here. Divergence
    #35.
    """
    from crm_app import mail
    from frappe_platform.models import User

    address = (user or extra.get("email") or "").strip()

    try:
        if address:
            # `iexact`, not a lowercased exact match. Frappe lowercases an email to form the
            # PK, but `Administrator` is the one account whose PK is not an email
            # (`AS_BUILT.md` §4) — so a lowercased lookup silently misses it, and the
            # exclusion below never runs.
            #
            # That was the first version, and it *looked* correct: asking to reset
            # Administrator sent no mail. It sent none because the row was not found, not
            # because it was excluded, and a later change to the lookup would have removed
            # the only thing standing there. Found by mutating the exclusion away and
            # watching the Administrator test keep passing.
            account = User._default_manager.filter(pk__iexact=address).first()
            # `user.py:1049` — Administrator is excluded, and a disabled account is not a
            # way in. Both fall through to the same response.
            if account and account.enabled and account.pk != "Administrator":
                raw_key = password_reset.issue_key(account)
                mail.send_password_reset(
                    to=account.email or account.pk,
                    reset_link=password_reset.reset_link(raw_key),
                    expiry_minutes=password_reset.expiry_minutes(),
                )
    except Exception:
        # `user.py:1055-1062` catches and logs three ways and answers identically. A mail
        # server that is down must not become a way to test whether an address exists.
        logger.warning("password reset failed for a requested address", exc_info=True)

    return {"message": GENERIC_RESET_RESPONSE}


@whitelist(
    "frappe.core.doctype.user.user.update_password",
    allow_guest=True,
    methods=("POST",),
)
@rate_limit(limit=20, seconds=60 * 60, key=lambda params: _throttle_identity(params))
def update_password(
    new_password: str = "",
    key: str = "",
    old_password: str = "",
    logout_all_sessions: int = 0,
    **extra,
):
    """`user.py:826-880` — set a password, by reset key or by old password.

    Returns a **token pair**, not a redirect. Upstream ends with
    `login_manager.login_as(user)` and returns a path; this port issues JWTs (phase 0's
    sanctioned deviation), so the page stores what `frontend/src/auth/tokens.js` expects.

    **Upstream's three outcomes are preserved as status codes**, because
    `update-password.html` branches on them and a client written against Frappe will too:

    * **200** — done, with tokens
    * **401** — the old password was wrong
    * **410** — the link is expired, used, or invalid

    `test_password_strength` is **not** ported (`PHASE_8_AUTH_AND_DESK.md`): it costs a
    round trip per keystroke and a rule the server does not enforce does not belong on the
    server. The real minimum is enforced here through Django's `AUTH_PASSWORD_VALIDATORS`,
    where a client that does not run our JavaScript cannot skip it.
    """
    from frappe_core.api.auth import issue_tokens

    if not new_password:
        throw("New password is required")
    if len(new_password) > MAX_PASSWORD_SIZE:
        # `user.py:839-840`, message verbatim.
        throw("Password size exceeded the maximum allowed size.")

    if key:
        resolution = password_reset.resolve_key(key)
        if not resolution.ok:
            # 410 Gone — upstream's status for a dead link (`user.py:849-851`).
            raise LinkNoLongerValid(resolution.message)
        account = resolution.user
    elif old_password:
        account = _authenticate_with_old_password(extra, old_password)
    else:
        throw("Provide either a reset key or your current password")

    _validate_password(new_password, account)

    # **Claim the key before setting the password**, not after. Found by the phase-8 review:
    # resolving and clearing were two statements, so two requests arriving together could
    # both resolve and both set a password — and the second one wins silently. Whoever
    # holds a forwarded copy of the link *is* that second request.
    #
    # `consume_key` makes the clear conditional on the key still being the resolved one, so
    # exactly one caller can win. The loser gets the same 410 as any dead link.
    if key and not password_reset.consume_key(account, raw_key=key):
        raise LinkNoLongerValid(password_reset.INVALID_MESSAGE)

    account.set_password(new_password)
    account.save(update_fields=["password"])

    if not key:
        # The old-password path: no key was presented, but any outstanding reset link for
        # this account is now stale and should not survive a password change.
        password_reset.consume_key(account)

    if int(logout_all_sessions or 0):
        _blacklist_outstanding_tokens(account)

    return issue_tokens(account)


def _caller_username(params: dict) -> str:
    """Who the old-password path is acting for, normalised.

    Three sources because the endpoint accepts three: upstream reads `frappe.session.user`,
    this port has no session so a caller may name itself, and it may do so under either of
    two parameter names. Lower-cased and stripped, because an identity used as a throttle
    bucket that varies with case is a throttle a caller can multiply — the phase-8 review
    found exactly that on forgot-password.
    """
    from frappe_core.session import get_current_user

    return (
        params.get("usr") or params.get("user") or get_current_user() or ""
    ).strip().lower()


def _throttle_identity(params: dict) -> str:
    """What `update_password`'s rate limit counts against. One endpoint, two jobs.

    **The reset path returns `""`, so the bucket stays the IP alone, and that is correct.**
    The caller is anonymous and holds a key we have not resolved yet; the attacker we are
    stopping is guessing keys, and their address is the only thing we know about them.
    Bucketing on the key itself would invert the protection — a guesser would mint a fresh
    bucket with every guess and never meet the limit.

    **The signed-in path returns the account**, because there we know exactly who is
    asking. Bucketing that on the IP alone charges a shared address for its own users:
    everyone behind one office NAT — or one mobile carrier, where the sharing is far
    wider — draws down a single allowance of 20 an hour. `frappe_core/api/auth.py:52`
    declines to put a hard cap on `login` for this reason, and this endpoint was the other
    half of that inconsistency.

    Rotating usernames to mint buckets does not buy an attacker anything here:
    `_authenticate_with_old_password` runs `check_login_allowed(ip, username)`, which locks
    on **either** identity (`security.py:173-184`), so the IP tracker catches the rotation
    the bucket key no longer does. The two mechanisms answer different questions, which is
    why upstream uses both.
    """
    if params.get("key"):
        return ""
    return _caller_username(params)


def _authenticate_with_old_password(extra: dict, old_password: str):
    """`user.py:967-971` — the signed-in path.

    Upstream reads `frappe.session.user`; this port has no session, so the caller names
    itself and proves it with the old password.

    **This checks a password on an `allow_guest` endpoint, so it goes through the login
    lockout.** Found by the phase-8 review: without it, the endpoint is an online password
    oracle that sidesteps `check_login_allowed` entirely — `login` is protected by an
    IP-and-account attempt tracker (`frappe_core/api/auth.py:52`), and a second door that
    checks passwords without it makes that protection decorative.

    The endpoint carries a `@rate_limit` as well. They do different jobs: the rate limit
    caps requests per hour, and the tracker locks a *specific account* after a run of
    failures however they are spread out. On this path the cap is counted per account
    rather than per address — see `_throttle_identity` for why the reset path is not.
    """
    from django.contrib.auth import authenticate

    from frappe_core.security import (
        check_login_allowed,
        get_client_ip,
        record_login_failure,
        record_login_success,
    )

    username = _caller_username(extra)
    if not username or username == "guest":
        raise WrongPassword("Invalid password")

    ip_key = get_client_ip()
    check_login_allowed(ip_key, username)

    account = authenticate(username=username, password=old_password)
    if account is None:
        record_login_failure(ip_key, username)
        # 401 — upstream's status when the old password is wrong.
        raise WrongPassword("Invalid password")

    record_login_success(ip_key, username)
    return account


def _validate_password(new_password: str, account) -> None:
    """Django's configured validators, which `config/settings/base.py` already sets up.

    Raises the *first* message rather than all of them, matching how the rest of this port
    surfaces a `throw`. The frontend shows one line.
    """
    try:
        validate_password(new_password, user=account)
    except DjangoValidationError as exc:
        throw(exc.messages[0] if exc.messages else "Password is not strong enough")


def _blacklist_outstanding_tokens(account) -> None:
    """`logout_all_sessions`, given a real meaning here.

    Upstream drops the user's server-side sessions. This port has none, so the equivalent
    is blacklisting every outstanding **refresh** token — which is what `logout` already
    does for one.

    **An access token issued before this call stays valid until it expires** (five minutes,
    `SIMPLE_JWT.ACCESS_TOKEN_LIFETIME`), because verifying one consults no state. That is
    the same window `logout` has, and it is accepted rather than closed —
    `specs/KNOWN_ISSUES.md` **§6** states the trade and costs the three ways out.

    (This docstring said "§4" and phase 8's progress file said the same. Neither was true:
    the entry did not exist until it was written for real. Cited correctly now.)
    """
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    from rest_framework_simplejwt.tokens import RefreshToken

    for token in OutstandingToken.objects.filter(user=account):
        try:
            RefreshToken(token.token).blacklist()
        except Exception:
            # Already blacklisted, or expired past parsing. Neither is a failure of the
            # thing being asked for.
            continue


#: `crm_invitation.py:66-72` — accepting an invitation grants the named role and the ones
#: it implies. Transcribed rather than inferred: a System Manager who did not also get
#: Sales User would be unable to see a lead.
IMPLIED_ROLES = {
    "System Manager": ("Sales Manager", "Sales User"),
    "Sales Manager": ("Sales User",),
    "Sales User": (),
}


@whitelist("crm.api.accept_invitation", allow_guest=True, methods=("GET", "POST"))
@rate_limit(limit=10, seconds=60 * 60)
def accept_invitation(key: str = "", **extra):
    """`crm/api/__init__.py:79-106` — redeem an invitation.

    **The key comes from the email, never from the API.** `CRM Invitation` is manager-only
    and its `key` is in `SENSITIVE_FIELDS`, both put in place before this endpoint existed
    precisely so that building it could not quietly open bug #21 — where upstream lets any
    Sales User read a pending invitation's key and redeem it. `KNOWN_ISSUES.md` §2 says so
    in as many words: *"do not remove it to make redemption easier."* Nothing here does.

    Rate-limited, as upstream is (`api/__init__.py:81`): the key is a bearer token and an
    unlimited endpoint is a guessing machine.

    **Returns a set-password link rather than redirecting.** Upstream sets
    `frappe.local.response["type"] = "redirect"` to a Desk URL; this port has no Desk, and
    the pages live in the Vue app. The caller is a browser following a link from an email,
    so the response says where to go next and the page performs it.
    """

    from crm_app.models import CRMInvitation

    if not key:
        # `api/__init__.py:84-85`, message verbatim — and identical to the not-found case
        # below, deliberately: a key that never existed and a key that is absent are the
        # same non-answer.
        throw("Invalid or expired key")

    invitation = CRMInvitation._default_manager.filter(key=key).first()
    if invitation is None:
        throw("Invalid or expired key")

    is_new_user = accept(invitation)

    account = _user_for(invitation.email)
    if is_new_user:
        # A brand-new account has no password. Mint a **reset** key — one hour, like any
        # other (`PHASE_8_AUTH_AND_DESK.md`: two clocks, three days to accept and one hour
        # to choose a password once you have).
        raw_key = password_reset.issue_key(account)
        return {
            "status": "set_password",
            "redirect_to": password_reset.reset_link(raw_key),
        }

    # An existing user already has a password; upstream logs them straight in. Here that
    # means tokens, which is the same thing in this port's terms.
    from frappe_core.api.auth import issue_tokens

    return {"status": "logged_in", "redirect_to": "/crm", **issue_tokens(account)}


def accept(invitation) -> bool:
    """`crm_invitation.py:60-80`. Returns whether the user was newly created.

    Never existed in this port — the endpoint that calls it was never built
    (`KNOWN_ISSUES.md` §2), so neither was this.

    The key is cleared here, as upstream does (`:77`), which is what makes redemption
    single-use.
    """
    from django.utils import timezone

    from crm_app.models import CRMInvitation

    if invitation.status != "Pending":
        # `crm_invitation.py:62`, verbatim. An accepted or expired invitation answers the
        # same as a fabricated key.
        throw("Invalid or expired key")

    # **Claim it first, atomically.** The status check above reads; this writes only if the
    # row is *still* Pending with *this* key. Two requests arriving together both pass the
    # read — the phase-8 review's point — and without this both would create the account
    # and grant roles. One row updated means this caller won.
    claimed = CRMInvitation._default_manager.filter(
        pk=invitation.pk, status="Pending", key=invitation.key
    ).update(status="Accepted", accepted_at=timezone.now(), key="")
    if not claimed:
        throw("Invalid or expired key")

    account, is_new_user = _create_user_if_not_exists(invitation.email)
    _grant_roles(account, invitation.role)
    return is_new_user


def _user_for(email: str):
    from frappe_platform.models import User

    return User._default_manager.filter(pk=str(email).strip().lower()).first()


def _create_user_if_not_exists(email: str):
    """`crm_invitation.py:92-100`.

    The account is created **enabled and with no usable password** — it cannot be logged
    into until the reset key mints one, and `set_unusable_password` is what makes that true
    rather than leaving an empty-string password that some backend might accept.
    """
    from frappe_platform.models import User

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


def _grant_roles(account, role: str) -> None:
    """`crm_invitation.py:66-72` — the named role plus the ones it implies."""
    from django.contrib.auth.models import Group

    for name in (role, *IMPLIED_ROLES.get(role, ())):
        group, _ = Group.objects.get_or_create(name=name)
        account.groups.add(group)


class WrongPassword(ValidationError):
    """401 — `update_password` with a bad `old_password` (`user.py`'s auth failure)."""

    http_status_code = 401


class LinkNoLongerValid(ValidationError):
    """410 — expired, used, or invalid (`user.py:849-851`).

    A distinct class rather than a flag on the message, because the **status code** is what
    `update-password.html` branches on and what a client written against a Frappe backend
    will branch on too.
    """

    http_status_code = 410
