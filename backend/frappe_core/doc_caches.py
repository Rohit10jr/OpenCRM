"""C3 - the two underscore caches nothing was writing.

``_assign`` has had a writer since phase 0 (:mod:`frappe_core.assignment`). ``_comments``
and ``_user_tags`` were ported as columns with no maintainer, so they stayed empty
forever - the comment preview in list views was always blank, and tags could not be set.

The two work differently, which is worth stating because it decides where the code lives:

* **``_comments`` is derived.** ``Comment`` rows are the source of truth and the column
  is a cache, so it is rebuilt by signal - exactly like ``_assign`` over ``ToDo``.
* **``_user_tags`` is the storage.** Frappe has no per-document tag table; the column
  itself holds the tags (``frappe/desk/doctype/tag/tag.py:105-118``), and the ``Tag``
  doctype only holds the tag *names*. So there is nothing to derive - what was missing is
  the add/remove helpers, which the phase-3 endpoints will call.

Both write with a bare ``update()``: these are cache refreshes, not document edits, so
they must not bump ``modified`` or re-stamp ``modified_by``. Upstream is explicit about
this - ``update_modified=False`` at ``tag.py:114``.
"""

from __future__ import annotations

import json

from django.db.models.signals import post_delete, post_save

from frappe_core import registry

#: ``comment.py:130-131`` - the preview is truncated, not the stored comment.
_COMMENT_PREVIEW_LIMIT = 100
_COMMENT_PREVIEW_KEEP = 97

#: ``comment.py:195`` - only the last 100 entries are cached.
_COMMENT_CACHE_LIMIT = 100


def _truncate(content: str) -> str:
    """``comment.py:130-131``."""
    content = content or ""
    if len(content) > _COMMENT_PREVIEW_LIMIT:
        return content[:_COMMENT_PREVIEW_KEEP] + "..."
    return content


def _cacheable(model) -> bool:
    return hasattr(model, "_comments")


def rebuild_comment_cache(doctype: str, name) -> list | None:
    """Recompute one document's ``_comments`` from its ``Comment`` rows.

    Upstream mutates the cached list in place (append, or update the matching entry).
    Rebuilding from the source reaches the same result and cannot drift - the same
    reasoning as ``assignment.rebuild_assign_cache``.

    **Only ``comment_type="Comment"`` counts** (``comment.py:127-128``); likes,
    assignments and the rest share the table but are not comments.
    """
    if not registry.has_doctype(doctype):
        return None
    model = registry.get_model(doctype)
    if not _cacheable(model):
        return None

    from frappe_platform.models import Comment

    rows = (
        Comment.objects.filter(
            reference_doctype=doctype, reference_name=str(name), comment_type="Comment"
        )
        .exclude(content="")
        .order_by("creation")
    )

    cached = [
        {
            "comment": _truncate(row.content),
            # "comment_email" for a Comment, "sender" for a Communication; owner is the
            # fallback (comment.py:146).
            "by": row.comment_email or row.owner_id or "",
            "name": row.pk,
        }
        for row in rows
    ][-_COMMENT_CACHE_LIMIT:]

    model._default_manager.filter(pk=name).update(_comments=cached)
    return cached


def _on_comment_write(sender, instance, **kwargs):
    if instance.reference_doctype and instance.reference_name:
        rebuild_comment_cache(instance.reference_doctype, instance.reference_name)


# --- tags -------------------------------------------------------------------------


def get_tags(doc) -> list[str]:
    """The document's tags, as a list. ``tag.py:83-85``."""
    raw = (getattr(doc, "_user_tags", "") or "").strip()
    return [t for t in raw.split(",") if t]


def _write_tags(doc, tags: list[str]) -> str:
    """``tag.py:105-114``.

    Stored with a **leading comma** when non-empty - ``"," + ",".join(...)`` - which is
    what makes upstream's ``_user_tags LIKE '%,tag,%'`` searches work
    (``tag.py:62``). Reproduced exactly; a list that merely looked right would break
    those queries.
    """
    unique_tags: list[str] = []
    for tag in tags:
        tag = (tag or "").strip()
        if tag and tag not in unique_tags:
            unique_tags.append(tag)

    value = ("," + ",".join(unique_tags)) if unique_tags else ""

    model = type(doc)
    # update(), not save(): tagging must not bump `modified` (tag.py:114).
    model._default_manager.filter(pk=doc.pk).update(_user_tags=value)
    doc._user_tags = value
    return value


def add_tag(doc, tag: str) -> str:
    """``tag.py:88-95``. Creates the ``Tag`` row if it does not exist yet."""
    from frappe_platform.models import Tag

    tags = get_tags(doc)
    if tag not in tags:
        tags.append(tag)
        Tag.objects.get_or_create(pk=tag)
    return _write_tags(doc, tags)


def remove_tag(doc, tag: str) -> str:
    """``tag.py:97-100``. Case-insensitive, as upstream is."""
    lowered = (tag or "").lower()
    return _write_tags(doc, [t for t in get_tags(doc) if t.lower() != lowered])


def remove_all_tags(doc) -> str:
    """``tag.py:102-104`` - upstream calls this before deleting a document."""
    return _write_tags(doc, [])


def connect_signals() -> None:
    from frappe_platform.models import Comment

    post_save.connect(_on_comment_write, sender=Comment, dispatch_uid="frappe_core.comments.save")
    post_delete.connect(
        _on_comment_write, sender=Comment, dispatch_uid="frappe_core.comments.delete"
    )
