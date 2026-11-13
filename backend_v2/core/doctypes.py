"""Small model metadata readers used in place of Frappe's doctype registry."""


def doctype_of(model) -> str:
    """Return the Frappe doctype declared by a model, or its class name."""
    return str(getattr(model, "DOCTYPE", model.__name__))


def is_child_table(model) -> bool:
    """Return whether a model represents an inline child table."""
    return bool(getattr(model, "IS_CHILD_TABLE", False))
