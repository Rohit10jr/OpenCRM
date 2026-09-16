"""Rows that hang off another document: `Comment`, `Communication`, `File`.

Each of these is *about* something else, and carries which something in a pair of fields.
So the rule is the same for all three, and it is the only rule that makes sense:

    **Defer to the referenced document.** Read it if you can read the parent; write it if
    you can write the parent.

Without it, the attachment leaked what the record itself refused. Confirmed by driving the
real route as a plain Sales User against a deal she is refused:

    GET  /api/resource/CRM Deal/<bob's deal>  -> 403
    GET  /api/resource/Communication          -> 200  the negotiating position, in prose
    GET  /api/resource/File                   -> 200  filename + URL of the contract
    GET  /api/resource/Comment                -> 200  what colleagues say to each other
    POST /api/resource/Comment                -> 201  forged onto that same deal

Worse than the record they hang off: a deal row leaks a number, its Communications leak
the reasoning.

### Why not upstream's Communication rule

Upstream hooks `Communication` too, but on a **different axis**
(`get_permission_query_conditions_for_communication`): it filters by which email accounts
the user owns. That is right for a mail client, where the question is "is this my mail?",
and wrong here, where the question is "may I see this deal?". Porting it verbatim would
have been faithful and useless. `File`'s upstream rule is the one with the right shape
(`frappe/core/doctype/file/file.py:908`), and it is what all three follow.

`Comment` has no hook upstream at all - it leans on role permissions granting only System
Manager and Website Manager. That is the same "no hook means no protection" trap as bug
#14: upstream had a layer this port does not model.

### One hop, not transitive

A Comment on a Communication on an invisible Deal is checked against the *Communication*,
not the Deal. Upstream does not chase the chain either, and doing so would need cycle
detection for a case the product does not produce. Stated so nobody assumes otherwise.
"""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from frappe_core import permissions, registry
from frappe_core.session import get_current_user

#: The doctypes this module governs. Excluded from each other's reference checks so the
#: subquery below cannot recurse - see "One hop, not transitive".
#:
#: `WhatsApp Message` joined in phase 7. It is the same shape - a row about a lead or deal,
#: carrying which one - and the reason is sharper than for the others: a deal row leaks a
#: number, but a WhatsApp thread leaks the conversation.
DEFERRING_DOCTYPES = ("Comment", "Communication", "File", "WhatsApp Message")

#: doctype -> (doctype field, name field). `File` spells them differently.
REFERENCE_FIELDS = {
    "Comment": ("reference_doctype", "reference_name"),
    "Communication": ("reference_doctype", "reference_name"),
    "File": ("attached_to_doctype", "attached_to_name"),
    "WhatsApp Message": ("reference_doctype", "reference_name"),
}


def _restricted_doctypes() -> list[str]:
    """Reference targets that actually restrict anything.

    A row pointing at a doctype with no rule needs no check - everyone can see the parent,
    so everyone can see the attachment. Only doctypes with a row rule can hide a parent,
    which keeps the subquery below to the two or three that matter rather than one branch
    per registered doctype.
    """
    from django.db.models import CharField

    targets = []
    for dt in registry.routable_doctypes():
        if dt in DEFERRING_DOCTYPES:
            continue
        entry = registry.get_entry(dt)
        if entry.permission_query_conditions is None:
            continue
        # The reference column is a `CharField`, so a doctype with an integer primary key
        # can never be a valid target - `CRM View Settings` has a `BigAutoField` and is
        # the live example. Including it does not merely waste a branch: Postgres refuses
        # `character varying = bigint` outright and the whole query dies.
        if not isinstance(entry.model._meta.pk, CharField):
            continue
        targets.append(dt)
    return targets


def _query_conditions(doctype: str, user: str | None = None):
    """Exclude rows whose parent is hidden.

    Expressed as a **subquery per restricted doctype**, not a per-row check. Deferring row
    by row would be an N+1 across every timeline in the product - the C9 shape - and the
    timeline is the busiest read path there is.

    Rows with no reference, or a reference to something unrestricted, are kept: there is
    nothing to hide behind.
    """
    user = user or get_current_user()
    if user == "Administrator":
        return None

    from frappe_core.query import base_queryset

    dt_field, name_field = REFERENCE_FIELDS[doctype]

    hidden = Q()
    for target in _restricted_doctypes():
        visible = base_queryset(target, user).values("pk")
        hidden |= Q(**{dt_field: target}) & ~Q(**{f"{name_field}__in": visible})

    # `Q()` is an empty filter - negating it would exclude everything.
    return ~hidden if hidden else None


def _has_permission(doc, ptype: str, user: str | None, doctype: str):
    """Port of `file.py:908`'s tail, generalised to all three.

    Write, create and delete require **write** on the parent; everything else requires
    read. That asymmetry is upstream's and it is right: commenting on a record is an edit
    of that record's history, not a read of it.
    """
    user = user or get_current_user()
    if user == "Administrator":
        return True

    dt_field, name_field = REFERENCE_FIELDS[doctype]
    ref_doctype = getattr(doc, dt_field, "") or ""
    ref_name = getattr(doc, name_field, "") or ""

    if not ref_doctype or not ref_name:
        # Nothing to defer to. A standalone row hides nothing, and refusing it here would
        # break the orphan rows the product legitimately creates.
        return True

    if ref_doctype in DEFERRING_DOCTYPES or not registry.has_doctype(ref_doctype):
        return True

    try:
        parent = registry.get_entry(ref_doctype).model._default_manager.get(pk=ref_name)
    except (ObjectDoesNotExist, ValueError, TypeError):
        # A reference to something that does not exist grants nothing. Returning True
        # here would make a nonexistent parent the way around the rule.
        return False

    needed = "write" if ptype in ("write", "create", "delete") else "read"
    return permissions.check_object_permission(parent, needed, user)


def _file_short_circuits(doc, ptype: str, user: str) -> bool | None:
    """`file.py:908-920`, the part that is specific to files.

    A public file is public - that is what `is_private = 0` means, and the frontend serves
    brand logos and avatars through it. Your own upload is yours regardless of where it
    ended up attached.
    """
    if not getattr(doc, "is_private", True) and ptype in ("read", "select"):
        return True
    owner = getattr(doc, "owner_id", None) or getattr(doc, "owner", None)
    if owner and str(owner) == str(user):
        return True
    return None


def comment_query_conditions(doctype: str, user: str | None = None):
    return _query_conditions("Comment", user)


def comment_has_permission(doc, ptype: str = "read", user: str | None = None):
    return _has_permission(doc, ptype, user, "Comment")


def communication_query_conditions(doctype: str, user: str | None = None):
    return _query_conditions("Communication", user)


def communication_has_permission(doc, ptype: str = "read", user: str | None = None):
    return _has_permission(doc, ptype, user, "Communication")


def whatsapp_message_query_conditions(doctype: str, user: str | None = None):
    return _query_conditions("WhatsApp Message", user)


def whatsapp_message_has_permission(doc, ptype: str = "read", user: str | None = None):
    return _has_permission(doc, ptype, user, "WhatsApp Message")


def file_query_conditions(doctype: str, user: str | None = None):
    user = user or get_current_user()
    if user == "Administrator":
        return None
    base = _query_conditions("File", user)
    # file.py:918-922, then 932-951: public files and your own uploads are visible
    # whatever they hang off; anything else only through a document you may see. A
    # private file attached to nothing is its owner's alone (FINDINGS.md 22).
    allowed = Q(is_private=False) | Q(owner=user)
    attached = ~Q(attached_to_doctype="") & ~Q(attached_to_name="")
    via_parent = attached if base is None else (attached & base)
    return allowed | via_parent


def file_has_permission(doc, ptype: str = "read", user: str | None = None):
    user = user or get_current_user()
    if user == "Administrator":
        return True
    short_circuit = _file_short_circuits(doc, ptype, user)
    if short_circuit is not None:
        return short_circuit
    # file.py:932-951: past the public and own-upload short-circuits, only a file
    # attached to a document can be reached, through that document; a private file
    # attached to nothing is nobody's but its owner's - ``return False``. The
    # "an orphan hides nothing" carve-out is for comments and communications, not files
    # (FINDINGS.md 22). Creating one is still allowed: that is the upload itself.
    if ptype != "create" and not (
        getattr(doc, "attached_to_doctype", "") and getattr(doc, "attached_to_name", "")
    ):
        return False
    return _has_permission(doc, ptype, user, "File")
