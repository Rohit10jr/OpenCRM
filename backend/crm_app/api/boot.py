"""The boot values the CRM page needs before it draws anything:
``crm.www.crm.get_context_for_dev``.

Upstream (``crm/www/crm.py``) delivers one dict, ``get_boot()``, two ways. In production
Frappe renders ``crm/www/crm.html`` - the shell ``yarn build`` writes from
``frontend/index.html`` - and the frappe-ui vite plugin (``jinjaBootData``) has left a
``<script>`` in it that writes ``window["<key>"] = <value>`` for every key. Under
``yarn dev`` Vite serves the raw ``index.html``, no template runs, and ``main.js`` posts to
``get_context_for_dev`` instead, copying every key of the reply onto ``window`` before it
mounts.

This port serves no HTML, so the endpoint is the only source of these values and the
frontend calls it in both modes (``frontend/JWT_PATCH.md``, the third deviation). Two
consequences, both deliberate (``docs/FINDINGS.md`` 26):

* **No developer-mode gate.** Upstream refuses with "This method is only meant for
  developer mode" outside it, because a live site has the HTML path. Here production is
  a caller too. Nothing in the answer is secret: number formats, a timezone, three false
  flags and empty translation tables.
* **The name is kept**, "for_dev" and all, so the string the frontend sends is the
  string the guard test (``tests/test_phase3_endpoints.py``) and the route inventory see.

Only the keys this frontend reads are returned. Upstream's ``csrf_token`` (frappe-ui adds
it as a header the port ignores), ``site_name`` and ``socketio_port`` (frappe-ui's
socket.io client, replaced in phase 6), ``frappe_version``, ``default_route``,
``setup_complete`` and ``read_only_mode`` are read by nothing under ``frontend/src``.
"""

from __future__ import annotations

from django.conf import settings

from frappe_core.query import by_name
from frappe_core.session import GUEST_USER, get_current_user
from frappe_core.whitelist import whitelist
from frappe_platform.models import User


@whitelist("crm.www.crm.get_context_for_dev", allow_guest=True, methods=("POST",))
def get_context_for_dev():
    """``crm/www/crm.py:get_boot``, trimmed to what ``frontend/src`` reads.

    * ``sysdefaults`` - upstream is ``frappe.defaults.get_defaults()``: System Settings
      republished as global defaults on every save (``system_settings.py:213-218``).
      There is no System Settings doctype here, so the seven format keys come from
      ``settings.FRAPPE_SYSDEFAULTS``. ``utils/index.js:82`` reads
      ``window.sysdefaults.date_format`` with no guard, so ``sysdefaults`` must always be
      a dict carrying that key. ``currency`` is the "Default display currency" Link on
      System Settings (``system_settings.json:710-715``), empty on a fresh site until the
      setup wizard picks one; ``stores/meta.js:58`` and ``FieldLayout/Field.vue:358``
      show USD for an empty value, so it ships empty and is set from ``.env``.
    * ``timezone`` - ``{"system", "user"}`` as ``App.vue:43-44`` reads it: the caller's
      own ``time_zone`` when set, else the system zone; a guest gets the system zone
      twice, which is upstream's answer for a user row without one.
    * The three site flags are false: demo seeding was never ported (``PORT_PLAN.md``
      section 2) and this port is never a Frappe Cloud site (``desk.py:current_site_info``).
    * ``translated_messages`` / ``translated_doctypes`` / ``state_options`` are empty:
      no translation tables are ported, and ``state_options`` is India Compliance's
      state list, which upstream also answers ``{}`` without that app.
    """
    system_zone = settings.TIME_ZONE
    return {
        "sysdefaults": dict(settings.FRAPPE_SYSDEFAULTS),
        "timezone": {"system": system_zone, "user": _user_time_zone() or system_zone},
        "translated_messages": {},
        "translated_doctypes": [],
        "state_options": {},
        "is_demo_site": False,
        "demo_data_created": False,
        "is_fc_site": False,
    }


def _user_time_zone() -> str:
    """The caller's ``time_zone`` column, ``""`` for a guest or an unset one."""
    user = get_current_user()
    if user == GUEST_USER:
        return ""
    row = by_name(User, user).only("time_zone").first()
    return (row.time_zone if row is not None else "") or ""
