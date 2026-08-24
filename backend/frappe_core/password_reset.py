"""Password-reset keys — issue, verify, consume.

Ports `frappe/core/doctype/user/user.py`:

| Upstream | Here |
|---|---|
| `:383` `_reset_password` — generate, hash, store, build the link | :func:`issue_key` |
| `:945` `_get_user_for_update_password` — expiry and the two messages | :func:`resolve_key` |
| `:828` `update_password` — clears the key on success | :func:`consume_key` |

The endpoints live in `crm_app/api/auth_pages.py`; this is the mechanism, separated so it
can be tested without a request.

## The three properties worth stating

**Stored hashed.** `sha256_hash(key)` goes in the row; the raw key exists only in the
emailed link. A database dump yields nothing redeemable. Hashing rather than encrypting is
deliberate — encryption is reversible, so an encrypted key is still a working key to
whoever holds the encryption key.

**Single use.** Cleared on success (`user.py:875`). Redeemed once, dead.

**Two failure messages, and only two.** Upstream's wording, verbatim, because it is
user-facing copy:

* *"The reset password link has been expired"*
* *"The reset password link has either been used before or is invalid"*

The second **merges "already used" with "never existed" on purpose**, so a key cannot be
probed for existence. The first is separate because an expired link is a real user's real
problem and telling them to ask for another is the whole job. Do not add a third.

## Expiry: zero means an hour, not forever

Upstream reads `reset_password_link_expiry_duration` from System Settings and treats **0 as
"no expiry check at all"** (`user.py:955-962` — the `if reset_password_link_expiry and …`
short-circuits). A reset link that works forever turns a mail archive into a credential
store, which is the same defect phase 4 closed on invitation keys.

`PHASE_8_AUTH_AND_DESK.md` settles it: `PASSWORD_RESET_LINK_EXPIRY_MINUTES`, default 60, and
**zero is redefined as 60 rather than as infinity**. Divergence #34.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

#: `user.py:945-966`. Upstream's strings, verbatim — user-facing copy, and the pair is
#: chosen so the second reveals nothing about which of two things went wrong.
EXPIRED_MESSAGE = "The reset password link has been expired"
INVALID_MESSAGE = "The reset password link has either been used before or is invalid"

#: `frappe.generate_hash()` is 56 hex characters by default. `token_urlsafe(32)` is the
#: same order of entropy (256 bits) in a form that survives a URL without escaping.
KEY_BYTES = 32

DEFAULT_EXPIRY_MINUTES = 60


def expiry_minutes() -> int:
    """How long a reset key lives.

    **Zero means 60, not "never expires".** See the module docstring: upstream's zero
    disables the check entirely, and that is the one part of its behaviour this port
    refuses to reproduce.
    """
    configured = getattr(settings, "PASSWORD_RESET_LINK_EXPIRY_MINUTES", DEFAULT_EXPIRY_MINUTES)
    try:
        minutes = int(configured)
    except (TypeError, ValueError):
        return DEFAULT_EXPIRY_MINUTES
    return minutes if minutes > 0 else DEFAULT_EXPIRY_MINUTES


def hash_key(raw_key: str) -> str:
    """`frappe.utils.sha256_hash`. Plain SHA-256, hex.

    Not a password hash, and deliberately not: the input is 256 bits of cryptographic
    randomness, so there is nothing to brute-force and nothing for a slow KDF to protect.
    A slow hash here would only make every redemption slow.
    """
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def issue_key(user) -> str:
    """`user.py:383-399`. Returns the **raw** key — the only time it exists.

    Written with `update()` rather than `save()`: `save()` on `User` runs the full model
    save path, and this is called from an unauthenticated endpoint where the ambient user
    is `Guest`. Upstream uses `db_set` for the same reason.

    Issuing a second key invalidates the first, because there is one column. That is
    upstream's behaviour and it is the right one: "I didn't get the email, send another"
    must not leave two live links.
    """
    from frappe_platform.models import User

    raw_key = secrets.token_urlsafe(KEY_BYTES)
    User._default_manager.filter(pk=user.pk).update(
        reset_password_key=hash_key(raw_key),
        last_reset_password_key_generated_on=timezone.now(),
    )
    return raw_key


@dataclass
class KeyResolution:
    """The outcome of looking a key up. Exactly one of ``user`` / ``message`` is set."""

    user: object | None = None
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.user is not None and self.message is None


def resolve_key(raw_key: str) -> KeyResolution:
    """`user.py:945-966`. Find the user a key belongs to, or say which of two things is wrong.

    **Expiry is checked after the lookup, and that ordering is upstream's.** A key that
    never existed and a key that expired are different answers, and a key that was *used*
    is indistinguishable from one that never existed — because clearing it on use is what
    makes it look like it never existed.
    """
    from frappe_platform.models import User

    if not raw_key:
        return KeyResolution(message=INVALID_MESSAGE)

    user = User._default_manager.filter(reset_password_key=hash_key(raw_key)).first()
    if user is None:
        return KeyResolution(message=INVALID_MESSAGE)

    issued = user.last_reset_password_key_generated_on
    if issued is None:
        # A key with no issue time cannot be aged. Treat it as invalid rather than as
        # eternally valid — the failure direction has to be "refuse".
        return KeyResolution(message=INVALID_MESSAGE)

    if timezone.now() > issued + timedelta(minutes=expiry_minutes()):
        return KeyResolution(message=EXPIRED_MESSAGE)

    return KeyResolution(user=user)


def consume_key(user, raw_key: str | None = None) -> bool:
    """`user.py:874-875`. Clear it, so the link is dead. Returns whether *this* call won.

    **Compare-and-swap, not read-then-clear.** Found by the phase-8 review: resolving the
    key and clearing it were two statements, so two requests arriving together could both
    resolve successfully and both go on to set a password. The loser's password would win,
    silently, and whoever holds a forwarded copy of the link is exactly the second request.

    Passing ``raw_key`` makes the UPDATE conditional on the key still being the one that was
    resolved — one row updated means this caller cleared it, zero means somebody else got
    there first. The caller can then refuse rather than proceeding on a key it no longer
    holds.

    Both columns, not just the key: a stale issue timestamp left behind would age the next
    key against the wrong clock.
    """
    from frappe_platform.models import User

    rows = User._default_manager.filter(pk=user.pk)
    if raw_key is not None:
        rows = rows.filter(reset_password_key=hash_key(raw_key))

    updated = rows.update(reset_password_key="", last_reset_password_key_generated_on=None)
    return bool(updated)


def reset_link(raw_key: str) -> str:
    """The URL that goes in the email.

    A **frontend** route, not an API path. `PHASE_8_AUTH_AND_DESK.md`: the pages live
    inside the Vue app, and `router.js:222`'s redirect out of the SPA is the bug. Upstream's
    `/update-password?key=…` is a Jinja page on the same origin; ours is a route in the SPA,
    which is a different origin in development.
    """
    base = (getattr(settings, "FRONTEND_ORIGIN", "") or "").rstrip("/")
    return f"{base}/crm/update-password?key={raw_key}"
