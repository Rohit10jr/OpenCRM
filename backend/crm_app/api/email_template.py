"""``frappe.email.doctype.email_template.email_template.get_email_template`` - render a
template for the email composer (``EmailEditor.vue:297-313``).

Upstream is three lines: ``frappe.get_doc``, ``check_permission("read")``, then
``get_formatted_email(doc)``, which renders ``subject`` and ``response_`` through
``frappe.render_template`` with the document *dict itself* as the context - so a template
writes ``{{ first_name }}``, not ``{{ doc.first_name }}``.

``response_`` is a property, not a column: ``response_html`` when ``use_html`` is set,
otherwise ``response`` (``email_template.py:28-30``).
"""

from __future__ import annotations

from frappe_core import permissions, registry
from frappe_core.exceptions import DoesNotExistError
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.exceptions import throw
from frappe_core.query import by_name, parse_json_param
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

_ENVIRONMENT = None


def _jinja_environment():
    """``frappe/utils/jinja.py:get_jenv`` - the two settings that are load-bearing here.

    * **SandboxedEnvironment.** Template text is user-authored (anyone who can write an
      Email Template writes it) and is rendered server-side against a real document, so
      an unsandboxed environment is a server-side template injection hole:
      ``{{ ''.__class__.__mro__ }}`` and onwards.
    * **``undefined=DebugUndefined``.** An unknown name renders back as ``{{ name }}``
      instead of raising or vanishing. That is what makes a template written for a Deal
      survive being applied to a Lead - the composer shows the placeholder and the user
      fixes it by hand.

    Not ported: the filters, globals and template loader ``get_jenv`` installs. Those
    exist for Frappe's own page templates (``frappe.db.get_value`` inside a template, the
    app-wide macro loader); an email template rendered against one document dict needs
    none of them, and every one of them is a wider sandbox.
    """
    global _ENVIRONMENT
    if _ENVIRONMENT is None:
        from jinja2 import DebugUndefined
        from jinja2.sandbox import SandboxedEnvironment

        # autoescape off, as upstream's string rendering has it: the response body *is*
        # HTML, and an escaped one would reach the composer as visible markup.
        _ENVIRONMENT = SandboxedEnvironment(undefined=DebugUndefined, autoescape=False)
    return _ENVIRONMENT


def render_template(template: str | None, context: dict) -> str:
    """``frappe/utils/jinja.py:render_template``, the string branch (``jinja.py:110-120``)."""
    from jinja2 import TemplateError

    if not template:
        return ""
    # `jinja.py:111`. The sandbox refuses dunder access at render time anyway; upstream
    # refuses it before compiling, with this sentence, and it is user-facing copy.
    if ".__" in template:
        throw("Illegal template")
    try:
        return _jinja_environment().from_string(template).render(context)
    except TemplateError:
        # Upstream throws under this title with the template *and a full traceback* in
        # the message (`jinja.py:117-120`). The traceback is left out: it names server
        # paths, and this endpoint answers an ordinary user of the composer.
        throw(f"<pre>{template}</pre>", title="Jinja Template Error")


@whitelist("frappe.email.doctype.email_template.email_template.get_email_template")
def get_email_template(template_name: str, doc=None):
    """``frappe/email/doctype/email_template/email_template.py:52-58``.

    GET and POST, as upstream's bare ``@frappe.whitelist()`` allows: this only reads.

    ``doc`` is the lead or deal the composer is open on. It arrives as an object from
    ``EmailEditor.vue`` and as a JSON string from a query-string caller; upstream accepts
    both (``get_formatted_email`` json-loads a string). Anything that is neither renders
    against an empty context rather than erroring - with ``DebugUndefined`` that gives the
    template back with its placeholders intact, which is the same answer as a document
    that simply lacks the fields.
    """
    model = registry.get_model("Email Template")
    instance = by_name(model, template_name).first()
    if instance is None:
        raise DoesNotExistError(f"Email Template {template_name} not found")
    if not permissions.check_object_permission(instance, "read", get_current_user()):
        raise FrappePermissionError(
            f"No permission for Email Template {template_name}", title="Not Permitted"
        )

    context = parse_json_param(doc, {}) or {}
    if not isinstance(context, dict):
        context = {}

    body = instance.response_html if instance.use_html else instance.response
    return {
        "subject": render_template(instance.subject, context),
        "message": render_template(body, context),
    }
